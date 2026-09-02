"""EuroCode Compass - local, offline backend package.

For navigation only. Verify all clauses in the official Eurocode.
"""

from .pdf_loader import PageChunk, chunk_pdf, load_pdf_metadata
from .embedder import Embedder, DEFAULT_MODEL_NAME
from .database import VectorStore, DEFAULT_DB_PATH
from .indexer import Indexer, SearchHit
from .workspace import (
    RestorePlan,
    Workspace,
    WorkspaceDocument,
    WorkspaceError,
    load_session,
    plan_restore,
    resolve_document_ids,
    resolve_selected_id,
    save_session,
)
from .branding import APP_NAME, DISCLAIMER, NOT_AFFILIATED
from .equations import (
    Equation,
    EquationError,
    EquationLibrary,
)
from .flowchart import (
    Flowchart,
    FlowchartError,
    FlowEdge,
    FlowNode,
    NodeEquation,
    NodeRef,
    resolve_document_path,
)

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
    "Flowchart",
    "FlowchartError",
    "FlowEdge",
    "FlowNode",
    "NodeEquation",
    "NodeRef",
    "APP_NAME",
    "NOT_AFFILIATED",
    "Equation",
    "EquationError",
    "EquationLibrary",
    "resolve_document_path",
    "Workspace",
    "WorkspaceDocument",
    "WorkspaceError",
    "RestorePlan",
    "plan_restore",
    "resolve_document_ids",
    "resolve_selected_id",
    "save_session",
    "load_session",
]
