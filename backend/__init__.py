"""Eurocode Reader - local, offline backend package.

For navigation only. Verify all clauses in the official Eurocode.
"""

from .pdf_loader import PageChunk, chunk_pdf, load_pdf_metadata
from .embedder import Embedder, DEFAULT_MODEL_NAME
from .database import VectorStore, DEFAULT_DB_PATH
from .indexer import Indexer, SearchHit

__all__ = [
    "PageChunk",
    "chunk_pdf",
    "load_pdf_metadata",
    "Embedder",
    "DEFAULT_MODEL_NAME",
    "VectorStore",
    "DEFAULT_DB_PATH",
    "Indexer",
    "SearchHit",
]
