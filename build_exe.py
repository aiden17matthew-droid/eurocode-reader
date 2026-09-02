"""Package EuroCode Compass into a standalone Windows executable.

    python build_exe.py

The result runs on a machine with no Python, no pip and no internet: the
search model is packaged inside it, so the app is genuinely offline from the
first launch.

    python build_exe.py --onedir     a folder instead of one file - starts
                                     instantly, easier to inspect
    python build_exe.py --console    keep a console window for diagnostics
    python build_exe.py --fast       skip UPX compression (quicker build)

WHAT IS AND IS NOT PACKAGED
---------------------------
Included: the app, CustomTkinter's themes and fonts, matplotlib's data, the
PyMuPDF binaries, and the all-MiniLM-L6-v2 search model.

Never included: the engineer's own Eurocode PDFs, their search index,
workspaces, equation library or settings. Those are their documents and their
work - the build refuses to embed data/ so a copy of the .exe cannot leak
somebody's licensed standards to a colleague.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.branding import APP_NAME                     # noqa: E402
from backend.embedder import DEFAULT_MODEL_NAME           # noqa: E402

EXE_NAME = "EuroCodeCompass"
ENTRY_POINT = PROJECT_ROOT / "app.py"

DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"
SPEC_FILE = PROJECT_ROOT / f"{EXE_NAME}.spec"

# Packages whose data files and submodules PyInstaller cannot work out on its
# own - these load things by name at runtime.
COLLECT_ALL = (
    "customtkinter",        # theme JSON and bundled fonts
    "sentence_transformers",
    "transformers",
    "tokenizers",
    "huggingface_hub",
    "safetensors",
)

HIDDEN_IMPORTS = (
    "PIL._tkinter_finder",          # Pillow's Tk bridge, imported indirectly
    "sklearn.utils._typedefs",      # pulled in by some ST code paths
    "scipy.special.cython_special",
)

# Nothing here is used by the app, and each one is large.
EXCLUDES = (
    "PyQt5", "PyQt6", "PySide2", "PySide6",
    "IPython", "jupyter", "notebook", "nbconvert",
    "pytest", "sphinx", "pandas", "cv2",
    "torch.utils.tensorboard", "tensorboard",
    "matplotlib.tests", "numpy.tests",
)


def say(message: str = "") -> None:
    print(message, flush=True)


def fail(message: str) -> "NoReturn":            # type: ignore[valid-type]
    say(f"\nBUILD STOPPED: {message}")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Checks worth doing before a ten-minute build
# ---------------------------------------------------------------------------

def check_pyinstaller() -> None:
    try:
        import PyInstaller                                  # noqa: F401
    except ImportError:
        fail("PyInstaller is not installed. Run:\n"
             "    pip install pyinstaller")


def check_entry_point() -> None:
    if not ENTRY_POINT.is_file():
        fail(f"{ENTRY_POINT.name} is missing - run this from the project folder.")


def find_model() -> Path:
    """The packaged search model. Without it the .exe cannot search offline."""
    from backend.paths import bundled_model_home
    from backend.embedder import default_cache_dir

    for candidate in (bundled_model_home(), default_cache_dir()):
        if candidate is None:
            continue
        hub = Path(candidate) / "hub"
        if hub.is_dir() and any(hub.glob("models--*MiniLM*")):
            return Path(candidate)

    fail(f"The '{DEFAULT_MODEL_NAME}' model is not on this machine, so the\n"
         f"  build would produce an .exe that cannot search. Download it once:\n"
         f"    python download_model.py")


def warn_about_torch() -> None:
    """A CUDA build of torch adds a couple of gigabytes nobody needs."""
    try:
        import torch
    except ImportError:
        fail("torch is not installed. Run:\n"
             "    pip install torch --index-url https://download.pytorch.org/whl/cpu\n"
             "    pip install -r requirements.txt")

    version = getattr(torch, "__version__", "")
    if "+cu" in version or getattr(torch.version, "cuda", None):
        say(f"  NOTE: torch {version} is a CUDA build. The app only ever uses")
        say("        the CPU, and this will add well over a gigabyte to the")
        say("        result. A CPU-only torch makes a far smaller download:")
        say("          pip uninstall torch")
        say("          pip install torch --index-url https://download.pytorch.org/whl/cpu")
        say("")


def folder_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def stage_model(cache_home: Path) -> Path:
    """Copy just the search model into a staging folder to be packaged.

    The HuggingFace cache on a developer's machine holds every model they
    have ever pulled, plus lock files and stale revisions. Bundling the lot
    would add hundreds of megabytes of things this app never loads, so only
    the one model is copied, keeping the cache's own layout so the libraries
    find it unchanged.
    """
    source_hub = cache_home / "hub"
    wanted = [d for d in source_hub.glob("models--*MiniLM*") if d.is_dir()]
    if not wanted:
        fail(f"No MiniLM model found under {source_hub}.")

    staged = BUILD_DIR / "model_payload"
    if staged.exists():
        shutil.rmtree(staged, ignore_errors=True)
    (staged / "hub").mkdir(parents=True, exist_ok=True)

    for model_dir in wanted:
        # symlinks=False resolves the cache's links into real files, which is
        # what has to travel inside the executable.
        shutil.copytree(model_dir, staged / "hub" / model_dir.name,
                        symlinks=False,
                        ignore=shutil.ignore_patterns(".lock", "*.lock",
                                                      "*.incomplete"))
    return staged


# ---------------------------------------------------------------------------
# The build
# ---------------------------------------------------------------------------

def build_command(args, model_home: Path) -> list:
    separator = ";" if os.name == "nt" else ":"

    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--name", EXE_NAME,
        "--onedir" if args.onedir else "--onefile",
        "--console" if args.console else "--windowed",
        "--specpath", str(PROJECT_ROOT),
        "--distpath", str(DIST_DIR),
        "--workpath", str(BUILD_DIR),
    ]

    # The model, so the app searches offline on a machine that has never seen
    # HuggingFace. Laid out exactly as the cache expects, and found again at
    # runtime by backend.paths.bundled_model_home().
    command += ["--add-data",
                f"{model_home}{separator}models/huggingface"]  # staged copy

    for package in COLLECT_ALL:
        command += ["--collect-all", package]
    for module in HIDDEN_IMPORTS:
        command += ["--hidden-import", module]
    for module in EXCLUDES:
        command += ["--exclude-module", module]

    if args.fast:
        command.append("--noupx")

    icon = PROJECT_ROOT / "assets" / "icon.ico"
    if icon.is_file():
        command += ["--icon", str(icon)]

    command.append(str(ENTRY_POINT))
    return command


def main() -> int:
    parser = argparse.ArgumentParser(
        description=f"Package {APP_NAME} as a standalone Windows executable.")
    parser.add_argument("--onedir", action="store_true",
                        help="Build a folder rather than a single file. "
                             "Starts instantly; easier to inspect.")
    parser.add_argument("--console", action="store_true",
                        help="Keep a console window open for diagnostics.")
    parser.add_argument("--fast", action="store_true",
                        help="Skip UPX compression - quicker, slightly bigger.")
    args = parser.parse_args()

    say("=" * 70)
    say(f"  Packaging {APP_NAME}")
    say("=" * 70)
    say()

    check_entry_point()
    check_pyinstaller()
    warn_about_torch()

    cache_home = find_model()
    say(f"  model cache: {cache_home}")
    say("  staging just the search model...")
    model_home = stage_model(cache_home)
    say(f"  model:      {DEFAULT_MODEL_NAME}  "
        f"({folder_size(model_home) / 1e6:.0f} MB packaged, from a "
        f"{folder_size(cache_home) / 1e6:.0f} MB cache)")
    say(f"  entry:      {ENTRY_POINT.name}")
    say(f"  mode:       {'one folder' if args.onedir else 'one file'}, "
        f"{'console' if args.console else 'windowed'}")

    # The engineer's PDFs, index and workspaces are theirs. Nothing under
    # data/ is ever passed to PyInstaller - state it plainly rather than
    # relying on nobody adding it later.
    data_dir = PROJECT_ROOT / "data"
    if data_dir.is_dir():
        say(f"  excluded:   {data_dir.name}/ "
            f"({folder_size(data_dir) / 1e6:.0f} MB of your own documents "
            f"and index)")
    say()

    command = build_command(args, model_home)
    say("  running PyInstaller - this takes several minutes...")
    say()

    started = time.time()
    result = subprocess.run(command, cwd=str(PROJECT_ROOT))
    minutes = (time.time() - started) / 60

    if result.returncode != 0:
        fail(f"PyInstaller exited with code {result.returncode}. "
             f"The output above says why.")

    target = (DIST_DIR / EXE_NAME if args.onedir
              else DIST_DIR / f"{EXE_NAME}.exe")
    if not target.exists():
        fail(f"PyInstaller reported success but {target} is not there.")

    size = folder_size(target) if target.is_dir() else target.stat().st_size

    say()
    say("=" * 70)
    say(f"  Done in {minutes:.1f} minutes")
    say("=" * 70)
    say(f"  {target}")
    say(f"  {size / 1e6:.0f} MB")
    say()
    say("  Give the engineer this file. They need no Python, no pip and no")
    say("  internet connection.")
    say()
    if not args.onedir:
        say("  First launch takes 20-60 seconds: a one-file build unpacks")
        say("  itself to a temporary folder before starting. Later launches")
        say("  are quicker. Build with --onedir if that wait is unwelcome.")
        say()
    say("  Their PDFs, index, workspaces and equation library are written to")
    say(r"    %LOCALAPPDATA%\{}".format(APP_NAME))
    say("  so they survive upgrades and are never inside the executable.")
    say()
    return 0


if __name__ == "__main__":
    sys.exit(main())
