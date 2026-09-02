"""EuroCode Compass - entry point.

Run with:

    python app.py

An offline clause finder for Eurocode PDFs you already own.
For navigation only. Verify all clauses in the official Eurocode.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import customtkinter as ctk

from backend.database import DEFAULT_DB_PATH
from backend.indexer import Indexer
from ui.main_window import EurocodeReaderApp


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH,
                        help="Location of the local SQLite index")
    parser.add_argument("--theme", default="system",
                        choices=["system", "light", "dark"])
    parser.add_argument("--online", action="store_true",
                        help="Allow the model loader to contact HuggingFace "
                             "(only needed the very first time)")
    args = parser.parse_args()

    ctk.set_appearance_mode(args.theme)
    ctk.set_default_color_theme("blue")

    # Offline by default: the model must come from the local cache.
    indexer = Indexer(db_path=args.db, offline=not args.online)

    app = EurocodeReaderApp(indexer=indexer)
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
