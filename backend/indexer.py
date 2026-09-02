"""Orchestration: PDF -> chunks -> embeddings -> SQLite, plus vector search.

This is the entry point the CustomTkinter UI will call. It exposes two
operations:

    index_pdf(path)   one-time, offline processing of a Eurocode PDF
    search(query)     natural-language lookup returning page/clause pointers

POINTER ONLY: search returns locations and text snippets copied verbatim from
the engineer's own PDF. It never calculates, interprets or recommends.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

import numpy as np

from .branding import APP_NAME, DISCLAIMER
from .database import DEFAULT_DB_PATH, VectorStore
from .embedder import DEFAULT_MODEL_NAME, Embedder
from .pdf_loader import PageChunk, chunk_pdf, file_hash, load_pdf_metadata


EMBED_BATCH = 64          # chunks embedded + written per transaction

# Cosine similarity below this is treated as noise rather than a pointer.
# A weak match is worse than no match: it sends the engineer to a page that
# does not answer the question.
#
# Calibrated against BS EN 1991-1-1:2025: genuine on-topic queries scored
# 59.7%-67.8%, while off-topic queries from other Eurocode parts (piles,
# steel buckling, timber fire) peaked at 43.7% by matching material-density
# vocabulary. 0.45 sits in the empty gap between those two bands.
MIN_RELEVANCE = 0.45


@dataclass
class SearchHit:
    """A single pointer into the engineer's PDF."""

    chunk_id: int
    document_id: int
    document_title: str
    document_path: str
    page_number: int
    clause_ref: Optional[str]
    table_ref: Optional[str]
    snippet: str
    score: float

    @property
    def location_label(self) -> str:
        parts = [f"Page {self.page_number}"]
        if self.clause_ref:
            parts.append(f"Clause {self.clause_ref}")
        if self.table_ref:
            parts.append(self.table_ref)
        return " - ".join(parts)

    def __str__(self) -> str:
        return f"[{self.score:.3f}] {self.location_label}\n    {self.snippet}"


@dataclass
class IndexResult:
    document_id: int
    title: str
    page_count: int
    chunk_count: int
    already_indexed: bool


class Indexer:
    """Owns the store and the embedding model for the lifetime of the app."""

    def __init__(
        self,
        db_path: Path = DEFAULT_DB_PATH,
        model_name: str = DEFAULT_MODEL_NAME,
        offline: bool = False,
    ) -> None:
        self.store = VectorStore(db_path)
        self.embedder = Embedder(model_name=model_name, offline=offline)

    def close(self) -> None:
        self.store.close()

    def __enter__(self) -> "Indexer":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    # --- indexing ----------------------------------------------------------
    def index_pdf(
        self,
        pdf_path: Path,
        force: bool = False,
        progress: Optional[Callable[[str, int, int], None]] = None,
    ) -> IndexResult:
        """Read, chunk, embed and store one PDF.

        ``progress(stage, done, total)`` is called with stage in
        {"reading", "embedding"} so the UI can show a live progress bar.
        """
        pdf_path = Path(pdf_path).resolve()
        digest = file_hash(pdf_path)
        existing = self.store.find_document_by_hash(digest)

        if existing and not force:
            # Same file content already indexed - reuse it, but refresh the
            # path in case the engineer moved or renamed the PDF.
            if existing["file_path"] != str(pdf_path):
                self.store.update_file_path(int(existing["id"]), pdf_path)
            return IndexResult(
                document_id=int(existing["id"]),
                title=existing["title"],
                page_count=int(existing["page_count"]),
                chunk_count=int(existing["chunk_count"]),
                already_indexed=True,
            )

        if existing and force:
            self.store.delete_document(int(existing["id"]))

        meta = load_pdf_metadata(pdf_path)

        def on_page(done: int, total: int) -> None:
            if progress:
                progress("reading", done, total)

        chunks: List[PageChunk] = list(chunk_pdf(pdf_path, progress=on_page))
        if not chunks:
            raise ValueError(
                f"No extractable text found in '{pdf_path.name}'. "
                "Phase 1 supports text-based PDFs only (no scanned images)."
            )

        document_id = self.store.add_document(
            file_path=pdf_path,
            file_hash=digest,
            title=meta["title"],
            page_count=meta["page_count"],
            model_name=self.embedder.model_name,
            embedding_dim=self.embedder.dimension,
        )

        total_chunks = len(chunks)
        written = 0
        try:
            for start in range(0, total_chunks, EMBED_BATCH):
                batch = chunks[start:start + EMBED_BATCH]
                vectors = self.embedder.encode([c.text for c in batch])
                written += self.store.add_chunks(document_id, batch, vectors)
                if progress:
                    progress("embedding", written, total_chunks)
        except Exception:
            # Never leave a half-indexed document behind.
            self.store.delete_document(document_id)
            raise

        return IndexResult(
            document_id=document_id,
            title=meta["title"],
            page_count=meta["page_count"],
            chunk_count=written,
            already_indexed=False,
        )

    # --- searching ---------------------------------------------------------
    def search(
        self,
        query: str,
        top_k: int = 5,
        document_id: Optional[int] = None,
        min_score: float = 0.0,
    ) -> List[SearchHit]:
        """Return the top matching locations for a natural-language query."""
        query = (query or "").strip()
        if not query:
            return []

        ids, matrix = self.store.load_vectors(document_id)
        if not ids:
            return []

        query_vector = self.embedder.encode_one(query)
        # Both sides are L2-normalised, so the dot product is cosine similarity.
        scores = matrix @ query_vector

        k = min(top_k, len(ids))
        top = np.argpartition(-scores, k - 1)[:k]
        top = top[np.argsort(-scores[top])]

        selected = [(ids[i], float(scores[i])) for i in top
                    if float(scores[i]) >= min_score]
        if not selected:
            return []

        rows = self.store.get_chunks([cid for cid, _ in selected])
        score_by_id = dict(selected)

        return [
            SearchHit(
                chunk_id=int(row["id"]),
                document_id=int(row["document_id"]),
                document_title=row["doc_title"],
                document_path=row["doc_path"],
                page_number=int(row["page_number"]),
                clause_ref=row["clause_ref"],
                table_ref=row["table_ref"],
                snippet=row["snippet"],
                score=score_by_id[int(row["id"])],
            )
            for row in rows
        ]

    # --- library -----------------------------------------------------------
    def list_documents(self) -> List[dict]:
        return [dict(row) for row in self.store.list_documents()]

    def remove_document(self, document_id: int) -> None:
        self.store.delete_document(document_id)


# --- CLI harness (for testing Phase 1 before the UI exists) ------------------

def _cli() -> int:
    # Eurocode titles carry non-breaking hyphens and en dashes, which crash the
    # default cp1252 Windows console. Degrade gracefully instead.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):  # pragma: no cover - unusual streams
        pass

    parser = argparse.ArgumentParser(
        description=f"{APP_NAME} backend. {DISCLAIMER}"
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH,
                        help="SQLite index file")
    parser.add_argument("--offline", action="store_true",
                        help="Fail fast instead of contacting HuggingFace")
    sub = parser.add_subparsers(dest="command", required=True)

    p_index = sub.add_parser("index", help="Index a Eurocode PDF")
    p_index.add_argument("pdf", type=Path)
    p_index.add_argument("--force", action="store_true",
                         help="Re-index even if already stored")

    p_search = sub.add_parser("search", help="Search the index")
    p_search.add_argument("query", type=str)
    p_search.add_argument("-k", "--top-k", type=int, default=5)
    p_search.add_argument("--doc", type=int, default=None,
                          help="Restrict to one document id")
    p_search.add_argument("--min-score", type=float, default=MIN_RELEVANCE,
                          help=f"Relevance floor (default {MIN_RELEVANCE}); "
                               f"pass 0 to see weak matches too")

    sub.add_parser("list", help="List indexed documents")

    p_remove = sub.add_parser("remove", help="Delete a document from the index")
    p_remove.add_argument("document_id", type=int)

    args = parser.parse_args()

    with Indexer(db_path=args.db, offline=args.offline) as indexer:
        if args.command == "index":
            def show(stage: str, done: int, total: int) -> None:
                print(f"\r  {stage}: {done}/{total}", end="", flush=True)

            result = indexer.index_pdf(args.pdf, force=args.force, progress=show)
            print()
            if result.already_indexed:
                print(f"Already indexed: {result.title} "
                      f"(id={result.document_id}, {result.chunk_count} chunks)")
            else:
                print(f"Indexed '{result.title}': {result.page_count} pages, "
                      f"{result.chunk_count} chunks (id={result.document_id})")

        elif args.command == "search":
            hits = indexer.search(args.query, top_k=args.top_k,
                                  document_id=args.doc)
            relevant = [h for h in hits if h.score >= args.min_score]
            if not hits:
                print("No matches. Index a PDF first, or try different wording.")
            elif not relevant:
                best = max(h.score for h in hits)
                print("No relevant clauses found in this document.")
                print(f"(Highest match was only {best:.0%}, below the "
                      f"{args.min_score:.0%} relevance threshold.)")
                print("Try loading a different Eurocode part.")
            for hit in relevant:
                print(f"\n{hit.document_title}")
                print(hit)
            print(f"\n{DISCLAIMER}")

        elif args.command == "list":
            docs = indexer.list_documents()
            if not docs:
                print("No documents indexed yet.")
            for doc in docs:
                print(f"[{doc['id']}] {doc['title']} - {doc['page_count']} pages, "
                      f"{doc['chunk_count']} chunks\n    {doc['file_path']}")

        elif args.command == "remove":
            indexer.remove_document(args.document_id)
            print(f"Removed document {args.document_id}.")

    return 0


if __name__ == "__main__":
    sys.exit(_cli())
