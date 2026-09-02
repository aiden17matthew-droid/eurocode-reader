"""Where the app finds what it ships with, and where it keeps the engineer's work.

Running from a source checkout these are both the project folder, which is
what makes development straightforward. Inside a packaged .exe they are two
very different places, and getting them confused loses data:

  resource_dir()   read-only files bundled into the executable. For a
                   one-file build PyInstaller unpacks these to a temporary
                   folder and DELETES IT when the app closes.

  app_data_dir()   the index, settings, session and equation library. These
                   have to outlive the process and survive an upgrade, so
                   they live under the user's own AppData - never inside the
                   bundle, and never next to an .exe that may well sit in
                   Program Files where nothing is writable.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from .branding import APP_NAME

# Lets an engineer point a portable install at a USB stick, and lets the
# tests run against a scratch directory.
DATA_DIR_ENV = "EUROCODE_COMPASS_DATA"


def is_frozen() -> bool:
    """True when running from a PyInstaller build rather than source."""
    return bool(getattr(sys, "frozen", False))


def resource_dir() -> Path:
    """The folder holding files shipped with the app.

    Never write here: in a one-file build it is a temporary directory that
    disappears when the app exits.
    """
    if is_frozen():
        bundled = getattr(sys, "_MEIPASS", None)
        if bundled:
            return Path(bundled)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def app_data_dir() -> Path:
    """The folder holding everything the engineer creates.

    From a source checkout this is ``data/`` beside the code, so a clone
    stays self-contained. From a packaged build it is
    ``%LOCALAPPDATA%\\EuroCode Compass``.
    """
    override = os.environ.get(DATA_DIR_ENV)
    if override:
        return Path(override)

    if is_frozen():
        base = os.environ.get("LOCALAPPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Local"
        return root / APP_NAME

    return Path(__file__).resolve().parent.parent / "data"


def ensure_app_data_dir() -> Path:
    """The data folder, created if it is not there yet."""
    target = app_data_dir()
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return target


def bundled_model_home() -> Optional[Path]:
    """The HuggingFace cache shipped inside a packaged build, if any.

    Packaging the model means the app works on a machine that has never
    downloaded it and may never see the internet - which is the whole point
    of an offline tool.
    """
    candidate = resource_dir() / "models" / "huggingface"
    return candidate if (candidate / "hub").is_dir() else None


def describe() -> str:
    """One line for diagnostics and the About box."""
    mode = "packaged" if is_frozen() else "source"
    return (f"{APP_NAME} ({mode})\n"
            f"  resources: {resource_dir()}\n"
            f"  your data: {app_data_dir()}")
