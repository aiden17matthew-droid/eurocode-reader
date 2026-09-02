"""How the engineer likes the app to look.

Appearance and interface size, remembered between sessions in an app-private
file under data/. Pure data - no Tkinter - so it can be tested without a
display.

These are presentation preferences and nothing else. No setting here changes
what a search returns, what a clause says, or what appears on a node.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .branding import APP_NAME
from .paths import app_data_dir

SCHEMA_VERSION = 1
FILE_KIND = "eurocode-reader-settings"

# Under the engineer's own data folder, which in a packaged build is
# NOT inside the bundle - a one-file .exe unpacks to a temporary
# directory that is deleted on exit.
DEFAULT_SETTINGS_PATH = app_data_dir() / "settings.json"

# "System" follows whatever Windows is set to, and keeps following it.
APPEARANCE_MODES: Tuple[str, ...] = ("System", "Light", "Dark")
DEFAULT_APPEARANCE = "System"

# CustomTkinter scales widgets and their fonts together, so one control
# covers both "UI scaling" and "font size".
SCALE_CHOICES: Tuple[float, ...] = (0.9, 1.0, 1.25, 1.5, 1.75)
DEFAULT_SCALE = 1.0
MIN_SCALE, MAX_SCALE = 0.75, 2.0


def scale_label(scale: float) -> str:
    return f"{scale:.0%}"


def scale_from_label(label: str, fallback: float = DEFAULT_SCALE) -> float:
    try:
        return float(str(label).strip().rstrip("%")) / 100.0
    except (TypeError, ValueError):
        return fallback


@dataclass
class Settings:
    """Presentation preferences, and nothing more."""

    appearance: str = DEFAULT_APPEARANCE
    ui_scale: float = DEFAULT_SCALE
    path: Path = field(default=DEFAULT_SETTINGS_PATH, compare=False)

    def __post_init__(self) -> None:
        mode = str(self.appearance or "").strip().title()
        self.appearance = mode if mode in APPEARANCE_MODES else DEFAULT_APPEARANCE
        try:
            scale = float(self.ui_scale)
        except (TypeError, ValueError):
            scale = DEFAULT_SCALE
        # Clamp rather than reject: a hand-edited file should not lock the
        # engineer out of an app whose text is suddenly unreadable.
        self.ui_scale = max(MIN_SCALE, min(MAX_SCALE, scale))
        self.path = Path(self.path)

    @property
    def scale_percent(self) -> str:
        return scale_label(self.ui_scale)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": FILE_KIND,
            "schema_version": SCHEMA_VERSION,
            "appearance": self.appearance,
            "ui_scale": round(self.ui_scale, 4),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any],
                  path: Path = DEFAULT_SETTINGS_PATH) -> "Settings":
        if not isinstance(data, dict):
            return cls(path=path)
        return cls(
            appearance=data.get("appearance", DEFAULT_APPEARANCE),
            ui_scale=data.get("ui_scale", DEFAULT_SCALE),
            path=path,
        )

    # --- files ---------------------------------------------------------
    def save(self, path: Path = None) -> Path:
        target = Path(path or self.path or DEFAULT_SETTINGS_PATH)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(target.suffix + ".tmp")
        temp.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        temp.replace(target)
        self.path = target
        return target

    @classmethod
    def load(cls, path: Path = DEFAULT_SETTINGS_PATH) -> "Settings":
        """Read the saved preferences, or hand back the defaults.

        A missing or damaged settings file is never worth an error on
        startup - the app just looks the way it does out of the box.
        """
        path = Path(path)
        if not path.is_file():
            return cls(path=path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return cls(path=path)
        return cls.from_dict(data, path=path)


def choice_labels() -> List[str]:
    return [scale_label(s) for s in SCALE_CHOICES]


def describe(settings: Settings) -> str:
    """One line for the status bar."""
    return (f"{APP_NAME} appearance: {settings.appearance.lower()} theme, "
            f"interface at {settings.scale_percent}.")
