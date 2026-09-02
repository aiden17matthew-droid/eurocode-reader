"""Workspaces: a named snapshot of which Eurocodes are loaded and which
flowchart is on the canvas.

Pure data - no Tkinter, no indexer - so it can be validated and tested
without a display.

SAFETY MODEL
------------
Two kinds of file live here, and they are deliberately kept apart:

  a workspace file    written ONLY when the engineer clicks Save Workspace.
                      These are the rollback points. Nothing in this app ever
                      writes to one on its own.

  the session file    an app-private file under data/, rewritten on exit so
                      the next launch can resume. It is never the engineer's
                      named workspace, so a bad afternoon's work can never
                      overwrite last week's good save.

The flowchart is stored *inside* the workspace, not as a path to it. A
workspace that merely pointed at pile_design.json would silently change every
time that file was edited, which is the opposite of a rollback point.

WHAT A WORKSPACE IS NOT
-----------------------
It records which documents were open and what the engineer drew. It holds no
results, no calculations and no design decisions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .branding import APP_NAME, DISCLAIMER
from .paths import app_data_dir
from .flowchart import Flowchart, FlowchartError, _clean

SCHEMA_VERSION = 1

# Slugs inside saved files: they name the format, not the product, so they
# stay put through a rename - every workspace already on disk uses them.
FILE_KIND = "eurocode-reader-workspace"
SESSION_KIND = "eurocode-reader-session"

# Under the engineer's own data folder, which in a packaged build is
# NOT inside the bundle - a one-file .exe unpacks to a temporary
# directory that is deleted on exit.
DEFAULT_SESSION_PATH = app_data_dir() / "session.json"

WORKSPACE_SUFFIX = ".json"
MAX_NAME = 200



class WorkspaceError(ValueError):
    """A workspace file is malformed or cannot be read."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

@dataclass
class WorkspaceDocument:
    """One Eurocode PDF that was loaded when the workspace was saved.

    The PDF itself is never copied into the workspace - the engineer owns
    those files and they stay where they are. Only enough information to find
    and recognise them again is recorded.
    """

    title: str
    file_path: str
    file_hash: str = ""
    page_count: int = 0

    def __post_init__(self) -> None:
        self.title = _clean(self.title, MAX_NAME)
        self.file_path = str(self.file_path or "")
        self.file_hash = str(self.file_hash or "")
        try:
            self.page_count = max(0, int(self.page_count))
        except (TypeError, ValueError):
            self.page_count = 0

    @property
    def exists(self) -> bool:
        return bool(self.file_path) and Path(self.file_path).is_file()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "file_path": self.file_path,
            "file_hash": self.file_hash,
            "page_count": self.page_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkspaceDocument":
        if not isinstance(data, dict):
            raise WorkspaceError(
                f"Document entry must be an object, got {type(data).__name__}"
            )
        return cls(
            title=data.get("title", ""),
            file_path=data.get("file_path", ""),
            file_hash=data.get("file_hash", ""),
            page_count=data.get("page_count", 0),
        )

    @classmethod
    def from_index_row(cls, row: Dict[str, Any]) -> "WorkspaceDocument":
        """Build from one entry of ``Indexer.list_documents()``."""
        return cls(
            title=str(row.get("title", "")),
            file_path=str(row.get("file_path", "")),
            file_hash=str(row.get("file_hash", "")),
            page_count=int(row.get("page_count") or 0),
        )


# ---------------------------------------------------------------------------
# The workspace
# ---------------------------------------------------------------------------

@dataclass
class Workspace:
    """Which Eurocodes were loaded, and the flowchart that went with them."""

    name: str = "Untitled workspace"
    documents: List[WorkspaceDocument] = field(default_factory=list)
    flowchart: Optional[Flowchart] = None
    # Where the flowchart was last saved on its own, if anywhere. Purely
    # informational: the chart above is the authoritative copy.
    flowchart_path: Optional[str] = None
    # Which document the search dropdown was pointed at. None means "All
    # Loaded Documents". Optional and additive, so older workspace files
    # still open unchanged.
    selected_document_title: Optional[str] = None
    created_at: str = field(default_factory=_utc_now)
    modified_at: str = field(default_factory=_utc_now)
    schema_version: int = SCHEMA_VERSION

    # --- construction --------------------------------------------------
    @classmethod
    def from_state(
        cls,
        name: str,
        documents: Iterable[Dict[str, Any]],
        flowchart: Optional[Flowchart] = None,
        flowchart_path: Optional[Path] = None,
        selected_document_title: Optional[str] = None,
    ) -> "Workspace":
        """Snapshot the live app state.

        ``documents`` is what ``Indexer.list_documents()`` returns, so this
        module never has to know about the indexer.
        """
        return cls(
            name=_clean(name, MAX_NAME) or "Untitled workspace",
            documents=[WorkspaceDocument.from_index_row(d) for d in documents],
            flowchart=flowchart,
            flowchart_path=str(flowchart_path) if flowchart_path else None,
            selected_document_title=selected_document_title or None,
        )

    def touch(self) -> None:
        self.modified_at = _utc_now()

    @property
    def summary(self) -> str:
        docs = len(self.documents)
        nodes = len(self.flowchart.nodes) if self.flowchart else 0
        return (f"{docs} document(s), "
                f"{nodes} flowchart node(s)")

    # --- serialisation -------------------------------------------------
    def to_dict(self, kind: str = FILE_KIND) -> Dict[str, Any]:
        return {
            "kind": kind,
            "schema_version": self.schema_version,
            "disclaimer": DISCLAIMER,
            "name": self.name,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "documents": [d.to_dict() for d in self.documents],
            "selected_document_title": self.selected_document_title,
            "flowchart_path": self.flowchart_path,
            "flowchart": self.flowchart.to_dict() if self.flowchart else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any],
                  allowed_kinds: Tuple[str, ...] = (FILE_KIND,)) -> "Workspace":
        if not isinstance(data, dict):
            raise WorkspaceError("Workspace file must contain a JSON object")

        stated = data.get("kind")
        if stated is not None and stated not in allowed_kinds:
            raise WorkspaceError(
                f"Not a {APP_NAME} workspace (kind={stated!r})"
            )

        version = data.get("schema_version", SCHEMA_VERSION)
        try:
            version = int(version)
        except (TypeError, ValueError):
            raise WorkspaceError(f"Invalid schema_version: {version!r}")
        if version > SCHEMA_VERSION:
            raise WorkspaceError(
                f"This workspace was written by a newer version of the app "
                f"(schema {version}, this app understands {SCHEMA_VERSION})."
            )

        raw_docs = data.get("documents", [])
        if not isinstance(raw_docs, list):
            raise WorkspaceError("'documents' must be a list")

        chart = None
        raw_chart = data.get("flowchart")
        if raw_chart:
            try:
                chart = Flowchart.from_dict(raw_chart)
            except FlowchartError as exc:
                # A corrupt chart must not cost the engineer their document
                # list as well - reopen what can be reopened.
                raise WorkspaceError(
                    f"The workspace's flowchart could not be read: {exc}"
                ) from exc

        return cls(
            name=_clean(data.get("name", "Untitled workspace"), MAX_NAME)
                 or "Untitled workspace",
            documents=[WorkspaceDocument.from_dict(d) for d in raw_docs],
            flowchart=chart,
            flowchart_path=data.get("flowchart_path") or None,
            selected_document_title=data.get("selected_document_title") or None,
            created_at=data.get("created_at") or _utc_now(),
            modified_at=data.get("modified_at") or _utc_now(),
            schema_version=version,
        )

    # --- files ---------------------------------------------------------
    def save_json(self, path: Path, kind: str = FILE_KIND) -> Path:
        path = Path(path)
        if path.suffix.lower() != WORKSPACE_SUFFIX:
            path = path.with_suffix(WORKSPACE_SUFFIX)
        self.touch()
        path.parent.mkdir(parents=True, exist_ok=True)
        # Temp-file-then-replace: an interrupted save must never leave the
        # engineer with a half-written rollback point.
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(
            json.dumps(self.to_dict(kind), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        temp.replace(path)
        return path

    @classmethod
    def load_json(
        cls, path: Path,
        allowed_kinds: Tuple[str, ...] = (FILE_KIND,),
    ) -> "Workspace":
        path = Path(path)
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise WorkspaceError(f"Could not read {path.name}: {exc}") from exc
        except UnicodeDecodeError as exc:
            raise WorkspaceError(
                f"{path.name} is not a text file. A workspace is a .json file "
                f"saved by this app."
            ) from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise WorkspaceError(
                f"{path.name} is not valid JSON (line {exc.lineno}): {exc.msg}"
            ) from exc
        return cls.from_dict(data, allowed_kinds=allowed_kinds)


# ---------------------------------------------------------------------------
# Restoring
# ---------------------------------------------------------------------------

@dataclass
class RestorePlan:
    """What opening a workspace will actually have to do.

    Worked out before anything is indexed, so the engineer can be told what is
    about to happen - and what is missing - up front.
    """

    ready: List[WorkspaceDocument] = field(default_factory=list)
    to_index: List[WorkspaceDocument] = field(default_factory=list)
    missing: List[WorkspaceDocument] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return not self.missing

    def describe(self) -> str:
        parts = []
        if self.ready:
            parts.append(f"{len(self.ready)} already indexed")
        if self.to_index:
            parts.append(f"{len(self.to_index)} to index")
        if self.missing:
            parts.append(f"{len(self.missing)} missing")
        return ", ".join(parts) if parts else "nothing to load"


def _match_indexed(
    doc: WorkspaceDocument, existing: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """Find this workspace document in the local index, or None.

    Content hash first, so a renamed or moved PDF is still recognised; then
    path; then title, for a workspace shared between machines.
    """
    if doc.file_hash:
        for row in existing:
            if str(row.get("file_hash", "")) == doc.file_hash:
                return row
    if doc.file_path:
        for row in existing:
            if str(row.get("file_path", "")) == doc.file_path:
                return row
    wanted = doc.title.strip().casefold()
    if wanted:
        for row in existing:
            if str(row.get("title", "")).strip().casefold() == wanted:
                return row
    return None


def plan_restore(
    workspace: Workspace, existing_documents: Iterable[Dict[str, Any]]
) -> RestorePlan:
    """Sort a workspace's documents into already-here, needs-indexing, gone.

    ``existing_documents`` is ``Indexer.list_documents()``.
    """
    existing = list(existing_documents or [])

    plan = RestorePlan()
    for doc in workspace.documents:
        if _match_indexed(doc, existing) is not None:
            plan.ready.append(doc)
        elif doc.exists:
            plan.to_index.append(doc)
        else:
            plan.missing.append(doc)
    return plan


def resolve_selected_id(
    workspace: Workspace, existing_documents: Iterable[Dict[str, Any]]
) -> Optional[int]:
    """The index id of the document this workspace was searching, if any.

    Returns None when the workspace was searching everything, or when the
    remembered document is not in this machine's index.
    """
    if not workspace.selected_document_title:
        return None
    wanted = workspace.selected_document_title.strip().casefold()
    for row in existing_documents or []:
        if str(row.get("title", "")).strip().casefold() == wanted:
            return int(row["id"]) if row.get("id") is not None else None
    return None


def resolve_document_ids(
    workspace: Workspace, existing_documents: Iterable[Dict[str, Any]]
) -> List[int]:
    """Local index ids for this workspace's documents, in workspace order.

    Lets the UI select the engineer's restored Eurocode in the search
    dropdown instead of leaving them to pick it out of the list again.
    Documents the index does not have are simply skipped.
    """
    existing = list(existing_documents or [])
    found: List[int] = []
    for doc in workspace.documents:
        row = _match_indexed(doc, existing)
        if row is not None and row.get("id") is not None:
            doc_id = int(row["id"])
            if doc_id not in found:
                found.append(doc_id)
    return found


# ---------------------------------------------------------------------------
# The session file (app-private, never a named workspace)
# ---------------------------------------------------------------------------

def save_session(
    workspace: Workspace,
    workspace_path: Optional[Path] = None,
    path: Path = DEFAULT_SESSION_PATH,
) -> Path:
    """Record the live state so the next launch can resume it.

    Writes ONLY to the app's own session file. It never touches the file the
    engineer saved with Save Workspace - that is the whole point.
    """
    path = Path(path)
    payload = workspace.to_dict(kind=SESSION_KIND)
    payload["workspace_path"] = str(workspace_path) if workspace_path else None
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                    encoding="utf-8")
    temp.replace(path)
    return path


def load_session(
    path: Path = DEFAULT_SESSION_PATH,
) -> Tuple[Optional[Workspace], Optional[Path]]:
    """Read the last session, or (None, None) if there isn't a usable one.

    A missing or damaged session file is never an error the engineer has to
    deal with - the app just starts empty.
    """
    path = Path(path)
    if not path.is_file():
        return None, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        workspace = Workspace.from_dict(
            data, allowed_kinds=(SESSION_KIND, FILE_KIND)
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, WorkspaceError,
            FlowchartError):
        return None, None
    raw_path = data.get("workspace_path") if isinstance(data, dict) else None
    return workspace, Path(raw_path) if raw_path else None


def clear_session(path: Path = DEFAULT_SESSION_PATH) -> None:
    path = Path(path)
    try:
        path.unlink()
    except OSError:
        pass


# --- CLI harness ------------------------------------------------------------

def _cli() -> int:
    import argparse
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):  # pragma: no cover - unusual streams
        pass

    parser = argparse.ArgumentParser(
        description=f"{APP_NAME} workspace files. {DISCLAIMER}"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser("validate", help="Check a workspace file")
    p_validate.add_argument("path", type=Path)

    p_info = sub.add_parser("info", help="Summarise a workspace file")
    p_info.add_argument("path", type=Path)

    args = parser.parse_args()

    try:
        workspace = Workspace.load_json(
            args.path, allowed_kinds=(FILE_KIND, SESSION_KIND)
        )
    except WorkspaceError as exc:
        print(f"INVALID: {exc}")
        return 1

    if args.command == "validate":
        print(f"OK: '{workspace.name}' - {workspace.summary}, "
              f"schema {workspace.schema_version}")
        return 0

    print(f"{workspace.name}  (schema {workspace.schema_version})")
    print(f"  created  {workspace.created_at}")
    print(f"  modified {workspace.modified_at}\n")
    print(f"  Documents ({len(workspace.documents)}):")
    for doc in workspace.documents:
        mark = "present" if doc.exists else "MISSING"
        print(f"    [{mark:>7}] {doc.title} - {doc.page_count} pp")
        print(f"              {doc.file_path}")
    if workspace.flowchart:
        chart = workspace.flowchart
        print(f"\n  Flowchart '{chart.name}': {len(chart.nodes)} nodes, "
              f"{len(chart.edges)} connections")
        if workspace.flowchart_path:
            print(f"    last saved to {workspace.flowchart_path}")
    else:
        print("\n  No flowchart stored.")
    print(f"\n{DISCLAIMER}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_cli())
