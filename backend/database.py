"""Local SQLite storage for chunks and their vector embeddings.

Everything lives in a single .db file next to the app - no server, no cloud.
Vectors are stored as raw float32 BLOBs, which is compact and loads straight
back into numpy for similarity search.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

import numpy as np

from .paths import app_data_dir
from .pdf_loader import PageChunk

# Under the engineer's own data folder, which in a packaged build is
# NOT inside the bundle - a one-file .exe unpacks to a temporary
# directory that is deleted on exit.
DEFAULT_DB_PATH = app_data_dir() / "eurocode_index.db"

SCHEMA_VERSION = 1

_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path     TEXT    NOT NULL,
    file_hash     TEXT    NOT NULL UNIQUE,
    title         TEXT    NOT NULL,
    page_count    INTEGER NOT NULL,
    chunk_count   INTEGER NOT NULL DEFAULT 0,
    model_name    TEXT    NOT NULL,
    embedding_dim INTEGER NOT NULL,
    indexed_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id  INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number  INTEGER NOT NULL,
    chunk_index  INTEGER NOT NULL,
    clause_ref   TEXT,
    table_ref    TEXT,
    text         TEXT    NOT NULL,
    snippet      TEXT    NOT NULL,
    embedding    BLOB    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_page     ON chunks(document_id, page_number);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class VectorStore:
    """SQLite-backed store for indexed Eurocode documents."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # The UI indexes and searches on worker threads while the connection is
        # created on the main thread, so cross-thread use must be allowed. The
        # lock keeps those accesses serialised.
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._lock = threading.RLock()
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        self.conn.commit()

    # --- lifecycle ---------------------------------------------------------
    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "VectorStore":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    # --- documents ---------------------------------------------------------
    def find_document_by_hash(self, file_hash: str) -> Optional[sqlite3.Row]:
        cur = self.conn.execute(
            "SELECT * FROM documents WHERE file_hash = ?", (file_hash,)
        )
        return cur.fetchone()

    def list_documents(self) -> List[sqlite3.Row]:
        cur = self.conn.execute(
            "SELECT * FROM documents ORDER BY indexed_at DESC"
        )
        return cur.fetchall()

    def get_document(self, document_id: int) -> Optional[sqlite3.Row]:
        cur = self.conn.execute(
            "SELECT * FROM documents WHERE id = ?", (document_id,)
        )
        return cur.fetchone()

    def add_document(
        self,
        file_path: Path,
        file_hash: str,
        title: str,
        page_count: int,
        model_name: str,
        embedding_dim: int,
    ) -> int:
        with self._lock:
            cur = self.conn.execute(
                """
                INSERT INTO documents
                    (file_path, file_hash, title, page_count,
                     model_name, embedding_dim, indexed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(Path(file_path).resolve()),
                    file_hash,
                    title,
                    page_count,
                    model_name,
                    embedding_dim,
                    _utc_now(),
                ),
            )
            self.conn.commit()
            return int(cur.lastrowid)

    def delete_document(self, document_id: int) -> None:
        """Remove a document and (via ON DELETE CASCADE) all of its chunks."""
        with self._lock:
            self.conn.execute("PRAGMA foreign_keys = ON")
            self.conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
            self.conn.commit()

    def update_file_path(self, document_id: int, file_path: Path) -> None:
        """Keep the stored path current if the engineer moves the PDF."""
        with self._lock:
            self.conn.execute(
                "UPDATE documents SET file_path = ? WHERE id = ?",
                (str(Path(file_path).resolve()), document_id),
            )
            self.conn.commit()

    # --- chunks ------------------------------------------------------------
    def add_chunks(
        self,
        document_id: int,
        chunks: Sequence[PageChunk],
        embeddings: np.ndarray,
    ) -> int:
        """Insert a batch of chunks with their matching embedding rows."""
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"chunk/embedding count mismatch: "
                f"{len(chunks)} chunks vs {len(embeddings)} vectors"
            )
        if not chunks:
            return 0

        rows = [
            (
                document_id,
                chunk.page_number,
                chunk.chunk_index,
                chunk.clause_ref,
                chunk.table_ref,
                chunk.text,
                chunk.snippet,
                np.asarray(vector, dtype=np.float32).tobytes(),
            )
            for chunk, vector in zip(chunks, embeddings)
        ]
        with self._lock:
            self.conn.executemany(
                """
                INSERT INTO chunks
                    (document_id, page_number, chunk_index, clause_ref,
                     table_ref, text, snippet, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            self.conn.execute(
                "UPDATE documents SET chunk_count = chunk_count + ? WHERE id = ?",
                (len(rows), document_id),
            )
            self.conn.commit()
        return len(rows)

    def chunk_count(self, document_id: Optional[int] = None) -> int:
        if document_id is None:
            cur = self.conn.execute("SELECT COUNT(*) FROM chunks")
        else:
            cur = self.conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE document_id = ?",
                (document_id,),
            )
        return int(cur.fetchone()[0])

    # --- retrieval ---------------------------------------------------------
    def load_vectors(
        self, document_id: Optional[int] = None
    ) -> Tuple[List[int], np.ndarray]:
        """Load chunk ids and their vectors as an (n, dim) float32 matrix."""
        ids: List[int] = []
        vectors: List[np.ndarray] = []

        with self._lock:
            if document_id is None:
                cur = self.conn.execute(
                    "SELECT id, embedding FROM chunks ORDER BY id"
                )
            else:
                cur = self.conn.execute(
                    "SELECT id, embedding FROM chunks "
                    "WHERE document_id = ? ORDER BY id",
                    (document_id,),
                )
            for row in cur:
                ids.append(int(row["id"]))
                # Copy: the BLOB buffer is owned by the sqlite3 row.
                vectors.append(
                    np.frombuffer(row["embedding"], dtype=np.float32).copy()
                )

        if not vectors:
            return [], np.empty((0, 0), dtype=np.float32)
        return ids, np.vstack(vectors)

    def get_chunks(self, chunk_ids: Iterable[int]) -> List[sqlite3.Row]:
        """Fetch full chunk rows (with document title/path) by id."""
        ids = list(chunk_ids)
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        with self._lock:
            cur = self.conn.execute(
                f"""
                SELECT c.*, d.title AS doc_title, d.file_path AS doc_path
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE c.id IN ({placeholders})
                """,
                ids,
            )
            rows = {int(row["id"]): row for row in cur.fetchall()}
        return [rows[i] for i in ids if i in rows]
