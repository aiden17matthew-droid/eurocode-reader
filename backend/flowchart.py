"""Flowchart data model: nodes, edges, and JSON persistence.

Pure data - no Tkinter, no PDF, no embedding model - so it can be validated
and unit-tested without a display.

WHAT A FLOWCHART IS HERE
------------------------
An engineer's own design sequence, drawn by hand, where each step may point at
a page or clause in a Eurocode PDF they own. It is an organisational aid and a
navigation index.

WHAT IT IS NOT
--------------
Nothing here is evaluated. A node may carry an equation, but it is stored as
LaTeX and only ever handed to a typesetter to be drawn - there is no field for
a variable's value, a unit, a substitution or a result, and no code path that
computes one. A decision node stores the engineer's own prose ("Is the pile
slender?") and this module never resolves it. Edge labels ("Yes", "No") are
captions the engineer writes, not conditions the app tests. An equation on a
node means "this is the formula that applies here", never "here is the
answer". Engineering accountability stays with the human.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

SCHEMA_VERSION = 1

FILE_KIND = "eurocode-reader-flowchart"

DISCLAIMER = (
    "For navigation only. Verify all clauses in the official Eurocode."
)

# start/end are the terminators; process is a step; decision is an if/else
# fork whose branches the engineer labels and follows themselves.
NODE_KINDS = ("start", "process", "decision", "end")

MAX_TITLE = 200
MAX_NOTES = 4000
MAX_LABEL = 60
MAX_EQUATION = 1200


class FlowchartError(ValueError):
    """A flowchart file is malformed or internally inconsistent."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _clean(value: Any, limit: int) -> str:
    """Coerce to a trimmed string of bounded length."""
    text = "" if value is None else str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    return text[:limit]


# ---------------------------------------------------------------------------
# Eurocode reference
# ---------------------------------------------------------------------------

@dataclass
class NodeRef:
    """Where in a Eurocode PDF a node points.

    Three identifiers are stored on purpose:

      file_path      works immediately on the machine that made the flowchart
      document_title survives being shared with a colleague whose index has
                     the same standard under a different document id
      document_id    a fast local link, meaningless on anyone else's machine

    Resolution tries them in that order - see ``resolve_document_path``.
    """

    document_title: str
    file_path: str
    page_number: int
    document_id: Optional[int] = None
    clause_ref: Optional[str] = None
    table_ref: Optional[str] = None

    def __post_init__(self) -> None:
        self.document_title = _clean(self.document_title, MAX_TITLE)
        self.file_path = str(self.file_path or "")
        try:
            self.page_number = max(1, int(self.page_number))
        except (TypeError, ValueError):
            raise FlowchartError(
                f"Reference page number must be a whole number, "
                f"got {self.page_number!r}"
            )
        self.clause_ref = _clean(self.clause_ref, MAX_LABEL) or None
        self.table_ref = _clean(self.table_ref, MAX_LABEL) or None

    @property
    def label(self) -> str:
        """Human-readable pointer, matching the search results' wording."""
        parts = [f"Page {self.page_number}"]
        if self.clause_ref:
            parts.append(f"Clause {self.clause_ref}")
        if self.table_ref:
            parts.append(self.table_ref)
        return " - ".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_title": self.document_title,
            "file_path": self.file_path,
            "page_number": self.page_number,
            "document_id": self.document_id,
            "clause_ref": self.clause_ref,
            "table_ref": self.table_ref,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NodeRef":
        if not isinstance(data, dict):
            raise FlowchartError(f"Reference must be an object, got {type(data).__name__}")
        if "page_number" not in data:
            raise FlowchartError("Reference is missing 'page_number'")
        doc_id = data.get("document_id")
        return cls(
            document_title=data.get("document_title", ""),
            file_path=data.get("file_path", ""),
            page_number=data["page_number"],
            document_id=int(doc_id) if isinstance(doc_id, (int, float, str))
                        and str(doc_id).strip().lstrip("-").isdigit() else None,
            clause_ref=data.get("clause_ref"),
            table_ref=data.get("table_ref"),
        )


def resolve_document_path(
    ref: NodeRef, documents: Iterable[Dict[str, Any]]
) -> Optional[Path]:
    """Find the PDF a reference points at, on *this* machine.

    ``documents`` is what ``Indexer.list_documents()`` returns. Returns None if
    the file cannot be located, leaving it to the caller to ask the engineer.
    """
    if ref.file_path:
        candidate = Path(ref.file_path)
        if candidate.is_file():
            return candidate

    docs = list(documents or [])

    # The document id is only meaningful against this machine's own index.
    if ref.document_id is not None:
        for doc in docs:
            if int(doc["id"]) == ref.document_id:
                candidate = Path(doc["file_path"])
                if candidate.is_file():
                    return candidate

    # Shared flowcharts land here: same standard, different local id/path.
    if ref.document_title:
        wanted = ref.document_title.strip().casefold()
        for doc in docs:
            if str(doc["title"]).strip().casefold() == wanted:
                candidate = Path(doc["file_path"])
                if candidate.is_file():
                    return candidate

    return None


# ---------------------------------------------------------------------------
# Nodes and edges
# ---------------------------------------------------------------------------

@dataclass
class NodeEquation:
    """The formula shown on a node, as LaTeX.

    The node keeps its own copy of the expression rather than a pointer into
    the equation library, so a workflow shared with a colleague still draws
    correctly on a machine whose library has never seen it.

    It is a picture of a formula and nothing more. Nothing in this codebase
    evaluates it, substitutes into it, or derives a result from it.
    """

    latex: str
    name: str = ""

    def __post_init__(self) -> None:
        # A single expression: newlines would only break the typesetter.
        self.latex = _clean(self.latex, MAX_EQUATION).replace("\n", " ").strip()
        self.name = _clean(self.name, MAX_TITLE)
        if not self.latex:
            raise FlowchartError("An equation needs an expression.")

    @property
    def display_name(self) -> str:
        return self.name or "Equation"

    def to_dict(self) -> Dict[str, Any]:
        return {"latex": self.latex, "name": self.name}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NodeEquation":
        if not isinstance(data, dict):
            raise FlowchartError(
                f"An equation must be an object, got {type(data).__name__}"
            )
        if not data.get("latex"):
            raise FlowchartError("Equation is missing 'latex'")
        return cls(latex=data["latex"], name=data.get("name", ""))


@dataclass
class FlowNode:
    """One step in the engineer's workflow.

    Carries a title, free-text notes, an optional Eurocode pointer and an
    optional equation to display. There is no computable field here by
    design: the equation is drawn, never solved.
    """

    title: str
    kind: str = "process"
    notes: str = ""
    ref: Optional[NodeRef] = None
    equation: Optional[NodeEquation] = None
    x: float = 0.0                     # world coordinates of the node centre
    y: float = 0.0
    id: str = field(default_factory=_new_id)

    def __post_init__(self) -> None:
        self.kind = str(self.kind or "process").strip().lower()
        if self.kind not in NODE_KINDS:
            raise FlowchartError(
                f"Unknown node kind {self.kind!r}. "
                f"Expected one of: {', '.join(NODE_KINDS)}"
            )
        self.title = _clean(self.title, MAX_TITLE)
        self.notes = _clean(self.notes, MAX_NOTES)
        self.id = str(self.id or _new_id())
        try:
            self.x = float(self.x)
            self.y = float(self.y)
        except (TypeError, ValueError):
            raise FlowchartError(f"Node {self.id!r} has a non-numeric position")

    @property
    def display_title(self) -> str:
        return self.title or "(untitled step)"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "notes": self.notes,
            "ref": self.ref.to_dict() if self.ref else None,
            "equation": self.equation.to_dict() if self.equation else None,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FlowNode":
        if not isinstance(data, dict):
            raise FlowchartError(f"Node must be an object, got {type(data).__name__}")
        raw_ref = data.get("ref")
        raw_equation = data.get("equation")
        return cls(
            id=data.get("id") or _new_id(),
            kind=data.get("kind", "process"),
            title=data.get("title", ""),
            notes=data.get("notes", ""),
            ref=NodeRef.from_dict(raw_ref) if raw_ref else None,
            equation=(NodeEquation.from_dict(raw_equation)
                      if raw_equation else None),
            x=data.get("x", 0.0),
            y=data.get("y", 0.0),
        )


@dataclass
class FlowEdge:
    """A directional arrow from one node to another.

    ``label`` is a caption the engineer types ("Yes", "No", "if L/d > 10").
    It is never parsed or evaluated - it is there so a human reading the chart
    knows which branch is which.
    """

    source_id: str
    target_id: str
    label: str = ""

    def __post_init__(self) -> None:
        self.source_id = str(self.source_id or "")
        self.target_id = str(self.target_id or "")
        self.label = _clean(self.label, MAX_LABEL)
        if not self.source_id or not self.target_id:
            raise FlowchartError("An edge needs both a source and a target node")
        if self.source_id == self.target_id:
            raise FlowchartError("An edge cannot connect a node to itself")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FlowEdge":
        if not isinstance(data, dict):
            raise FlowchartError(f"Edge must be an object, got {type(data).__name__}")
        try:
            return cls(
                source_id=data["source_id"],
                target_id=data["target_id"],
                label=data.get("label", ""),
            )
        except KeyError as exc:
            raise FlowchartError(f"Edge is missing {exc.args[0]!r}") from exc


# ---------------------------------------------------------------------------
# The document
# ---------------------------------------------------------------------------

@dataclass
class Flowchart:
    """A named workflow: nodes, the arrows between them, and when it changed."""

    name: str = "Untitled workflow"
    nodes: List[FlowNode] = field(default_factory=list)
    edges: List[FlowEdge] = field(default_factory=list)
    created_at: str = field(default_factory=_utc_now)
    modified_at: str = field(default_factory=_utc_now)
    schema_version: int = SCHEMA_VERSION

    # --- lookups -------------------------------------------------------
    def node_by_id(self, node_id: str) -> Optional[FlowNode]:
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def edges_for(self, node_id: str) -> List[FlowEdge]:
        return [e for e in self.edges
                if e.source_id == node_id or e.target_id == node_id]

    # --- mutation ------------------------------------------------------
    def touch(self) -> None:
        self.modified_at = _utc_now()

    def add_node(self, node: FlowNode) -> FlowNode:
        if self.node_by_id(node.id) is not None:
            node.id = _new_id()
        self.nodes.append(node)
        self.touch()
        return node

    def remove_node(self, node_id: str) -> bool:
        node = self.node_by_id(node_id)
        if node is None:
            return False
        self.nodes.remove(node)
        # An edge to a deleted node would dangle - drop those too.
        self.edges = [e for e in self.edges
                      if e.source_id != node_id and e.target_id != node_id]
        self.touch()
        return True

    def add_edge(self, source_id: str, target_id: str, label: str = "") -> Optional[FlowEdge]:
        """Connect two nodes. Returns None if the connection is not allowed."""
        if source_id == target_id:
            return None
        if self.node_by_id(source_id) is None or self.node_by_id(target_id) is None:
            return None
        for existing in self.edges:
            if existing.source_id == source_id and existing.target_id == target_id:
                # Same arrow drawn twice - update the caption rather than
                # stacking two identical lines on top of each other.
                if label:
                    existing.label = _clean(label, MAX_LABEL)
                    self.touch()
                return existing
        edge = FlowEdge(source_id=source_id, target_id=target_id, label=label)
        self.edges.append(edge)
        self.touch()
        return edge

    def remove_edge(self, edge: FlowEdge) -> bool:
        if edge in self.edges:
            self.edges.remove(edge)
            self.touch()
            return True
        return False

    # --- validation ----------------------------------------------------
    def validate(self) -> List[str]:
        """Return a list of problems. Empty means the chart is consistent."""
        problems: List[str] = []

        seen = set()
        for node in self.nodes:
            if node.id in seen:
                problems.append(f"Duplicate node id: {node.id}")
            seen.add(node.id)
            if node.kind not in NODE_KINDS:
                problems.append(f"Node {node.id}: unknown kind {node.kind!r}")

        for edge in self.edges:
            if edge.source_id not in seen:
                problems.append(f"Edge points from a missing node: {edge.source_id}")
            if edge.target_id not in seen:
                problems.append(f"Edge points to a missing node: {edge.target_id}")

        return problems

    # --- serialisation -------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": FILE_KIND,
            "schema_version": self.schema_version,
            # Written into every file so a shared workflow carries its own
            # liability notice, even opened outside this app.
            "disclaimer": DISCLAIMER,
            "name": self.name,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Flowchart":
        if not isinstance(data, dict):
            raise FlowchartError("Flowchart file must contain a JSON object")

        stated_kind = data.get("kind")
        if stated_kind is not None and stated_kind != FILE_KIND:
            raise FlowchartError(
                f"Not a Eurocode Reader flowchart (kind={stated_kind!r})"
            )

        version = data.get("schema_version", SCHEMA_VERSION)
        try:
            version = int(version)
        except (TypeError, ValueError):
            raise FlowchartError(f"Invalid schema_version: {version!r}")
        if version > SCHEMA_VERSION:
            raise FlowchartError(
                f"This file was written by a newer version of the app "
                f"(schema {version}, this app understands {SCHEMA_VERSION})."
            )

        raw_nodes = data.get("nodes", [])
        raw_edges = data.get("edges", [])
        if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
            raise FlowchartError("'nodes' and 'edges' must both be lists")

        chart = cls(
            name=_clean(data.get("name", "Untitled workflow"), MAX_TITLE)
                 or "Untitled workflow",
            nodes=[FlowNode.from_dict(n) for n in raw_nodes],
            created_at=data.get("created_at") or _utc_now(),
            modified_at=data.get("modified_at") or _utc_now(),
            schema_version=version,
        )

        ids = {n.id for n in chart.nodes}
        for raw in raw_edges:
            edge = FlowEdge.from_dict(raw)
            # Silently dropping a dangling edge is kinder than refusing to open
            # a workflow that is otherwise fine.
            if edge.source_id in ids and edge.target_id in ids:
                chart.edges.append(edge)

        problems = chart.validate()
        if problems:
            raise FlowchartError("; ".join(problems))
        return chart

    # --- files ---------------------------------------------------------
    def save_json(self, path: Path) -> Path:
        path = Path(path)
        if path.suffix.lower() != ".json":
            path = path.with_suffix(".json")
        self.touch()
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write via a temporary file so an interrupted save cannot destroy the
        # engineer's existing workflow.
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        temp.replace(path)
        return path

    @classmethod
    def load_json(cls, path: Path) -> "Flowchart":
        path = Path(path)
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise FlowchartError(f"Could not read {path.name}: {exc}") from exc
        except UnicodeDecodeError as exc:
            # Picking a PDF or the index database in the file dialog must give
            # a clear message, not a traceback.
            raise FlowchartError(
                f"{path.name} is not a text file. A flowchart is a .json file "
                f"saved by this app."
            ) from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise FlowchartError(
                f"{path.name} is not valid JSON (line {exc.lineno}): {exc.msg}"
            ) from exc
        return cls.from_dict(data)


# --- CLI harness (validate a workflow file without launching the UI) --------

def _cli() -> int:
    import argparse
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):  # pragma: no cover - unusual streams
        pass

    parser = argparse.ArgumentParser(
        description=f"Eurocode Reader flowchart files. {DISCLAIMER}"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser("validate", help="Check a flowchart JSON file")
    p_validate.add_argument("path", type=Path)

    p_info = sub.add_parser("info", help="Summarise a flowchart JSON file")
    p_info.add_argument("path", type=Path)

    args = parser.parse_args()

    try:
        chart = Flowchart.load_json(args.path)
    except FlowchartError as exc:
        print(f"INVALID: {exc}")
        return 1

    if args.command == "validate":
        print(f"OK: '{chart.name}' - {len(chart.nodes)} nodes, "
              f"{len(chart.edges)} connections, schema {chart.schema_version}")
    else:
        print(f"{chart.name}  (schema {chart.schema_version})")
        print(f"  created  {chart.created_at}")
        print(f"  modified {chart.modified_at}")
        print(f"  {len(chart.nodes)} nodes, {len(chart.edges)} connections\n")
        for node in chart.nodes:
            pointer = f"  ->  {node.ref.document_title} {node.ref.label}" if node.ref else ""
            print(f"  [{node.kind:8}] {node.display_title}{pointer}")
        for edge in chart.edges:
            source = chart.node_by_id(edge.source_id)
            target = chart.node_by_id(edge.target_id)
            caption = f" ({edge.label})" if edge.label else ""
            print(f"  {source.display_title} --> {target.display_title}{caption}")
        print(f"\n{DISCLAIMER}")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_cli())
