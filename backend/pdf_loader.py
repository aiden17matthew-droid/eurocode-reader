"""PDF reading and page-by-page chunking using PyMuPDF (fitz).

This module is a *pointer* layer only: it extracts text and records where that
text lives (page number, clause reference, table reference). It never
interprets, computes or rewrites engineering content.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator, List, Optional

try:
    # PyMuPDF >= 1.24 prefers the 'pymupdf' name; 'fitz' is deprecated.
    import pymupdf as fitz
except ImportError:  # pragma: no cover - older PyMuPDF releases
    try:
        import fitz
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise ImportError(
            "PyMuPDF is required. Install it with:\n"
            "    pip install pymupdf"
        ) from exc


# --- Chunking configuration --------------------------------------------------
# MiniLM truncates at 256 word-pieces (~1000 characters). Staying under that
# keeps every chunk fully represented in its embedding.
MAX_CHUNK_CHARS = 900
CHUNK_OVERLAP_CHARS = 150
MIN_CHUNK_CHARS = 40
SNIPPET_CHARS = 320

# Eurocode headings look like "7.6.2.3 Ultimate limit state design" or
# "A.3.2 ...". Annex headings start with a letter.
_CLAUSE_HEADING = re.compile(
    r"^\s*((?:[A-H]|\d{1,2})(?:\.\d{1,2}){1,4})(?=[\s ]+\D|$)"
)
# "Table 7.5", "Table A.2", "Figure 3.1", and National Annex refs
# such as "Table A.NA.10".
#
# The keyword is matched case-insensitively but the reference itself is NOT:
# a case-insensitive letter would swallow the first character of an ordinary
# following word, turning "Annex and other standards" into "Annex a". The
# trailing (?![a-z]) guards the same mistake for the digit branch.
_TABLE_REF = re.compile(
    r"\b((?i:Table|Tab\.|Figure|Fig\.|Annex))\s+"
    r"((?:[A-H]|\d{1,2})(?:\.(?:NA|[A-H]|\d{1,2}))*)(?![a-z])"
)

_WHITESPACE = re.compile(r"[ \t ]+")
_BLANK_LINES = re.compile(r"\n\s*\n+")


@dataclass
class PageChunk:
    """One searchable unit of text, anchored to a physical PDF page."""

    page_number: int          # 1-based, matches what the engineer sees
    chunk_index: int          # order of this chunk within the whole document
    text: str                 # cleaned text used for embedding
    clause_ref: Optional[str] = None   # e.g. "7.6.2.3"
    table_ref: Optional[str] = None    # e.g. "Table 7.5"
    snippet: str = field(default="")   # short preview shown in the UI

    def __post_init__(self) -> None:
        if not self.snippet:
            self.snippet = build_snippet(self.text)

    @property
    def location_label(self) -> str:
        """Human-readable pointer, e.g. 'Page 142 - Clause 7.6.2.3'."""
        parts = [f"Page {self.page_number}"]
        if self.clause_ref:
            parts.append(f"Clause {self.clause_ref}")
        if self.table_ref:
            parts.append(self.table_ref)
        return " - ".join(parts)


# --- Text helpers ------------------------------------------------------------

def normalise_text(raw: str) -> str:
    """Collapse PDF whitespace artefacts without destroying paragraph breaks."""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("­", "")           # soft hyphens
    text = _WHITESPACE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _BLANK_LINES.sub("\n\n", text)
    return text.strip()


def build_snippet(text: str, limit: int = SNIPPET_CHARS) -> str:
    """Flatten a chunk into a one-line preview for the results list."""
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    cut = flat[:limit].rsplit(" ", 1)[0]
    return cut + "..."


def extract_clause_ref(text: str) -> Optional[str]:
    """Return the first clause-style heading found at the start of a line."""
    for line in text.split("\n"):
        match = _CLAUSE_HEADING.match(line)
        if match:
            return match.group(1).rstrip(".")
    return None


def extract_table_ref(text: str) -> Optional[str]:
    """Return the first Table/Figure/Annex reference mentioned in the text."""
    match = _TABLE_REF.search(text)
    if not match:
        return None
    label = match.group(1).rstrip(".").capitalize()
    return f"{label} {match.group(2)}"


def file_hash(pdf_path: Path, block_size: int = 1 << 20) -> str:
    """SHA-256 of the file, used to detect an already-indexed document."""
    digest = hashlib.sha256()
    with open(pdf_path, "rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


# --- Chunking ----------------------------------------------------------------

def split_page_text(text: str) -> List[str]:
    """Split one page into overlapping, embedding-sized pieces.

    Paragraphs are kept whole where possible; oversized paragraphs are hard-cut
    with a character overlap so a clause spanning the cut stays searchable.
    """
    if not text:
        return []
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]

    pieces: List[str] = []
    buffer = ""

    for paragraph in text.split("\n\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue

        if len(paragraph) > MAX_CHUNK_CHARS:
            if buffer:
                pieces.append(buffer)
                buffer = ""
            pieces.extend(_hard_split(paragraph))
            continue

        candidate = f"{buffer}\n\n{paragraph}" if buffer else paragraph
        if len(candidate) <= MAX_CHUNK_CHARS:
            buffer = candidate
        else:
            pieces.append(buffer)
            buffer = paragraph

    if buffer:
        pieces.append(buffer)
    return pieces


def _hard_split(paragraph: str) -> List[str]:
    """Cut an oversized paragraph into overlapping windows."""
    step = MAX_CHUNK_CHARS - CHUNK_OVERLAP_CHARS
    windows: List[str] = []
    start = 0
    while start < len(paragraph):
        window = paragraph[start:start + MAX_CHUNK_CHARS]
        # Prefer to end on a word boundary when more text follows.
        if start + MAX_CHUNK_CHARS < len(paragraph) and " " in window:
            window = window.rsplit(" ", 1)[0]
        windows.append(window.strip())
        start += max(step, len(window) - CHUNK_OVERLAP_CHARS, 1)
    return [w for w in windows if w]


def load_pdf_metadata(pdf_path: Path) -> dict:
    """Read title/page count without extracting any text."""
    with fitz.open(pdf_path) as doc:
        meta = doc.metadata or {}
        title = (meta.get("title") or "").strip() or Path(pdf_path).stem
        return {
            "title": title,
            "page_count": doc.page_count,
            "is_encrypted": doc.is_encrypted,
        }


def chunk_pdf(
    pdf_path: Path,
    progress: Optional[Callable[[int, int], None]] = None,
) -> Iterator[PageChunk]:
    """Yield PageChunk objects page by page for the whole document.

    ``progress`` is called as ``progress(pages_done, total_pages)`` so the UI
    can drive a progress bar during the one-time indexing pass.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    chunk_index = 0
    with fitz.open(pdf_path) as doc:
        if doc.is_encrypted and not doc.authenticate(""):
            raise ValueError(
                f"'{pdf_path.name}' is password protected and cannot be indexed."
            )

        total = doc.page_count
        current_clause: Optional[str] = None

        for page_no in range(total):
            page = doc.load_page(page_no)
            text = normalise_text(page.get_text("text"))

            if len(text) >= MIN_CHUNK_CHARS:
                for piece in split_page_text(text):
                    if len(piece) < MIN_CHUNK_CHARS:
                        continue
                    # A heading inside this piece wins; otherwise the clause
                    # carries over from earlier text (clauses span pages).
                    found = extract_clause_ref(piece)
                    if found:
                        current_clause = found
                    yield PageChunk(
                        page_number=page_no + 1,
                        chunk_index=chunk_index,
                        text=piece,
                        clause_ref=found or current_clause,
                        table_ref=extract_table_ref(piece),
                    )
                    chunk_index += 1

            if progress:
                progress(page_no + 1, total)
