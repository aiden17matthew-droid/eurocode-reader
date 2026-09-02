"""A global library of equations the engineer has typed out for reference.

Pure data - no Tkinter, no matplotlib - so it can be validated and tested
without a display.

WHAT AN EQUATION IS HERE
------------------------
A picture of a formula. The engineer writes the LaTeX for, say, the punching
shear expression in EN 1992-1-1, names it, and can then drop that picture onto
any flowchart node so a reader can see which expression the step refers to.

WHAT IT IS NOT
--------------
It is never solved. There is deliberately no field for a variable's value, a
unit, a substitution or a result, and nothing in this codebase evaluates the
stored string - it is only ever handed to a typesetter to be drawn. An
equation on a node means "this is the formula you need", never "here is the
answer". The arithmetic, and the accountability for it, stay with the
engineer.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .branding import APP_NAME, DISCLAIMER, NOT_CALCULATED

SCHEMA_VERSION = 1

# The slug inside saved files: it names the format, not the product, so it
# stays put through a rename - every library already on disk uses it.
FILE_KIND = "eurocode-reader-equation-library"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LIBRARY_PATH = PROJECT_ROOT / "data" / "equations.json"

MAX_NAME = 120
MAX_LATEX = 1200
MAX_NOTE = 600



class EquationError(ValueError):
    """An equation or library file is malformed."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _clean(value: Any, limit: int) -> str:
    """Trim to a bounded single-line-ish string, dropping control characters."""
    text = "" if value is None else str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(ch for ch in text if ch == "\n" or ch >= " ")
    return text.strip()[:limit]


@dataclass
class Equation:
    """One named formula, stored as the LaTeX the engineer typed."""

    name: str
    latex: str
    # Where it came from and what it is for, in the engineer's own words.
    note: str = ""
    source: str = ""
    id: str = field(default_factory=_new_id)
    created_at: str = field(default_factory=_utc_now)
    modified_at: str = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        self.name = _clean(self.name, MAX_NAME)
        # LaTeX is a single expression: newlines would only break the parser.
        self.latex = _clean(self.latex, MAX_LATEX).replace("\n", " ").strip()
        self.note = _clean(self.note, MAX_NOTE)
        self.source = _clean(self.source, MAX_NAME)
        self.id = str(self.id or _new_id())
        if not self.name:
            raise EquationError("An equation needs a name.")
        if not self.latex:
            raise EquationError(f"'{self.name}' has no equation in it.")

    @property
    def key(self) -> str:
        """Case-insensitive identity, for spotting a name already in use."""
        return self.name.strip().casefold()

    def touch(self) -> None:
        self.modified_at = _utc_now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "latex": self.latex,
            "note": self.note,
            "source": self.source,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Equation":
        if not isinstance(data, dict):
            raise EquationError(
                f"An equation must be an object, got {type(data).__name__}"
            )
        try:
            return cls(
                id=data.get("id") or _new_id(),
                name=data.get("name", ""),
                latex=data.get("latex", ""),
                note=data.get("note", ""),
                source=data.get("source", ""),
                created_at=data.get("created_at") or _utc_now(),
                modified_at=data.get("modified_at") or _utc_now(),
            )
        except EquationError as exc:
            raise EquationError(f"Bad equation entry: {exc}") from exc


class EquationLibrary:
    """Every equation the engineer has saved, across all their workflows.

    Deliberately global rather than per-workspace: an office's standard set of
    expressions should be typed once, not once per project.
    """

    def __init__(self, equations: Optional[Iterable[Equation]] = None,
                 path: Optional[Path] = None) -> None:
        self.equations: List[Equation] = list(equations or [])
        self.path: Optional[Path] = Path(path) if path else None

    # --- lookups -------------------------------------------------------
    def __len__(self) -> int:
        return len(self.equations)

    def __iter__(self):
        return iter(self.equations)

    def names(self) -> List[str]:
        return [e.name for e in self.sorted()]

    def sorted(self) -> List[Equation]:
        return sorted(self.equations, key=lambda e: e.name.casefold())

    def by_name(self, name: str) -> Optional[Equation]:
        wanted = (name or "").strip().casefold()
        for equation in self.equations:
            if equation.key == wanted:
                return equation
        return None

    def by_id(self, equation_id: str) -> Optional[Equation]:
        for equation in self.equations:
            if equation.id == equation_id:
                return equation
        return None

    # --- mutation ------------------------------------------------------
    def save_equation(self, equation: Equation) -> Equation:
        """Add a new equation, or update the one with the same name.

        Saving over an existing name is how an engineer corrects a formula, so
        it replaces in place and keeps the original id - anything already
        pointing at it keeps working.
        """
        existing = self.by_name(equation.name)
        if existing is None:
            self.equations.append(equation)
            return equation

        existing.latex = equation.latex
        existing.note = equation.note
        existing.source = equation.source
        existing.touch()
        return existing

    def remove(self, name: str) -> bool:
        equation = self.by_name(name)
        if equation is None:
            return False
        self.equations.remove(equation)
        return True

    def rename(self, old_name: str, new_name: str) -> bool:
        equation = self.by_name(old_name)
        if equation is None:
            return False
        cleaned = _clean(new_name, MAX_NAME)
        if not cleaned:
            raise EquationError("An equation needs a name.")
        clash = self.by_name(cleaned)
        if clash is not None and clash is not equation:
            raise EquationError(f"'{cleaned}' is already in the library.")
        equation.name = cleaned
        equation.touch()
        return True

    # --- serialisation -------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": FILE_KIND,
            "schema_version": SCHEMA_VERSION,
            "disclaimer": DISCLAIMER,
            # Written into the file so a shared library carries the same
            # warning as everything else this app saves.
            "note": NOT_CALCULATED,
            "equations": [e.to_dict() for e in self.sorted()],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EquationLibrary":
        if not isinstance(data, dict):
            raise EquationError("An equation library must be a JSON object")

        stated = data.get("kind")
        if stated is not None and stated != FILE_KIND:
            raise EquationError(
                f"Not a {APP_NAME} equation library (kind={stated!r})"
            )

        version = data.get("schema_version", SCHEMA_VERSION)
        try:
            version = int(version)
        except (TypeError, ValueError):
            raise EquationError(f"Invalid schema_version: {version!r}")
        if version > SCHEMA_VERSION:
            raise EquationError(
                f"This library was written by a newer version of the app "
                f"(schema {version}, this app understands {SCHEMA_VERSION})."
            )

        raw = data.get("equations", [])
        if not isinstance(raw, list):
            raise EquationError("'equations' must be a list")

        library = cls()
        for entry in raw:
            # One damaged entry must not cost the engineer the whole library.
            try:
                library.save_equation(Equation.from_dict(entry))
            except EquationError:
                continue
        return library

    # --- files ---------------------------------------------------------
    def save_json(self, path: Optional[Path] = None) -> Path:
        target = Path(path or self.path or DEFAULT_LIBRARY_PATH)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Temp-file-then-replace: an interrupted save must never destroy a
        # library built up over months.
        temp = target.with_suffix(target.suffix + ".tmp")
        temp.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        temp.replace(target)
        self.path = target
        return target

    @classmethod
    def load_json(cls, path: Path) -> "EquationLibrary":
        path = Path(path)
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise EquationError(f"Could not read {path.name}: {exc}") from exc
        except UnicodeDecodeError as exc:
            raise EquationError(
                f"{path.name} is not a text file. An equation library is a "
                f".json file saved by this app."
            ) from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise EquationError(
                f"{path.name} is not valid JSON (line {exc.lineno}): {exc.msg}"
            ) from exc
        library = cls.from_dict(data)
        library.path = path
        return library

    @classmethod
    def load_or_empty(cls, path: Path = DEFAULT_LIBRARY_PATH) -> "EquationLibrary":
        """Open the global library, or start a fresh one.

        A missing or damaged library is never an error the engineer has to
        deal with on launch - they just start with an empty palette.
        """
        path = Path(path)
        if not path.is_file():
            return cls(path=path)
        try:
            return cls.load_json(path)
        except EquationError:
            return cls(path=path)


# --- CLI harness ------------------------------------------------------------

def _cli() -> int:
    import argparse
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):  # pragma: no cover - unusual streams
        pass

    parser = argparse.ArgumentParser(
        description=f"{APP_NAME} equation library. {NOT_CALCULATED}"
    )
    parser.add_argument("--library", type=Path, default=DEFAULT_LIBRARY_PATH)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="List saved equations")
    p_show = sub.add_parser("show", help="Show one equation's LaTeX")
    p_show.add_argument("name")
    sub.add_parser("validate", help="Check the library file")

    args = parser.parse_args()

    try:
        library = EquationLibrary.load_json(args.library)
    except EquationError as exc:
        print(f"INVALID: {exc}")
        return 1

    if args.command == "validate":
        print(f"OK: {len(library)} equation(s), schema {SCHEMA_VERSION}")
    elif args.command == "list":
        if not len(library):
            print("The library is empty.")
        for equation in library.sorted():
            print(f"  {equation.name}")
            print(f"      {equation.latex}")
            if equation.source:
                print(f"      source: {equation.source}")
    else:
        equation = library.by_name(args.name)
        if equation is None:
            print(f"No equation named '{args.name}'.")
            return 1
        print(equation.latex)

    print(f"\n{NOT_CALCULATED}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_cli())
