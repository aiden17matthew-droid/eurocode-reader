"""What the application calls itself.

One place for the name, so a rename never again means hunting through
dialogs, window titles and command-line help.

Note what is deliberately NOT here: the ``kind`` strings written inside saved
workspace, flowchart and equation files. Those stay as they are
("eurocode-reader-workspace" and friends) because they identify a file
format, not a product. Renaming them would make every file the engineer has
already saved unopenable.
"""

from __future__ import annotations

APP_NAME = "EuroCode Compass"

APP_TAGLINE = "Offline Eurocode clause finder and design workflow builder"

WINDOW_TITLE = f"{APP_NAME} - offline clause finder"

# Shown in the header under the title.
APP_SUBTITLE = (
    "Search your own Eurocode PDFs offline. "
    "Results point to a page and clause - nothing more."
)

# The liability notice carried on every screen and written into every file.
DISCLAIMER = (
    "For navigation only. Verify all clauses in the official Eurocode."
)

# Required wording: this is a private tool, not a standards publication.
NOT_AFFILIATED = (
    f"{APP_NAME} is a local workflow tool. Not affiliated with CEN or BSI."
)

NOT_CALCULATED = (
    "Equations are visual references only. This app never evaluates, "
    "substitutes into, or solves them."
)

OFFLINE_NOTE = (
    "Everything runs on this machine. No internet connection, no API keys, "
    "and no document ever leaves your computer."
)

ABOUT_LINES = (
    f"{APP_NAME}",
    APP_TAGLINE,
    "",
    "Search, read and cross-reference the Eurocode PDFs you already own, "
    "and build design workflows that point at them.",
    "",
    OFFLINE_NOTE,
    "",
    NOT_CALCULATED,
    "",
    DISCLAIMER,
    "",
    NOT_AFFILIATED,
)
