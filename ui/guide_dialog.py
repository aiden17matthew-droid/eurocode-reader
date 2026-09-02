"""The built-in user guide.

Written for an engineer who has just opened the app for the first time, and
who has not read the source. Each tab says what the feature is for, how to
drive it, and - where it matters - what it deliberately will not do.

The content lives in GUIDE as plain data so the wording can be edited without
touching any layout code.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import customtkinter as ctk

from backend.branding import APP_NAME, DISCLAIMER, NOT_AFFILIATED

from .smooth_scroll import smooth_scroll

MUTED = "#8a8a8a"
ACCENT = "#3b8ed0"
WARNING = "#e0a800"

# tab -> list of (heading, [paragraph, ...])
Section = Tuple[str, List[str]]

GUIDE: Dict[str, List[Section]] = {
    "Getting started": [
        ("What this app is", [
            f"{APP_NAME} is a compass for the Eurocode PDFs you already own. "
            "It helps you find the right clause quickly, keep a record of the "
            "route you took, and put your own design workflow on paper.",
            "Everything runs on this machine. There is no internet "
            "connection, no account and no upload - your PDFs never leave "
            "your computer.",
        ]),
        ("The three tabs", [
            "Search - ask a question in plain English and get pointed at the "
            "pages that answer it.",
            "Flowchart Builder - draw your design sequence, with each step "
            "linked to the clause it depends on.",
            "Both share the same documents, and a result can be sent from "
            "one to the other in a single click.",
        ]),
        ("First run", [
            "1. Go to the Search tab and click Load PDF. Pick a Eurocode you "
            "own. The one-time indexing takes a minute or two for a long "
            "standard; it never has to be repeated.",
            "2. Type a question and press Enter.",
            "3. Click a result to open that exact page.",
            "You can also build your equation library first, before loading "
            "anything - see the Equations tab of this guide.",
        ]),
    ],
    "Search": [
        ("Ask in your own words", [
            "The search is semantic, not a keyword match. It compares the "
            "meaning of your question against the meaning of each passage, "
            "so 'how much load do I put on an office floor' finds the "
            "imposed-load categories even though none of those words appear "
            "in the clause heading.",
            "That also means spelling out what you actually want works "
            "better than typing two keywords. 'shear resistance of bored "
            "piles' beats 'pile shear'.",
        ]),
        ("Reading the results", [
            "Each result shows the page, the clause or table it sits in, a "
            "verbatim snippet of the text, and a match percentage.",
            "The match percentage is a retrieval score, not an engineering "
            "confidence. It says how closely the wording matches your "
            "question - nothing about whether the clause is the right one "
            "for your design.",
            "Click a result to open that page in a read-only viewer.",
        ]),
        ("The relevance threshold", [
            "Results below 45% are hidden by default. A weak match is "
            "usually a false pointer, and being sent to an unrelated page is "
            "worse than being told there is nothing.",
            "If you are hunting for wording the model scores badly, or you "
            "suspect the answer is in there somewhere, tick 'Include weak "
            "matches'. Everything below the threshold is then shown, each "
            "one clearly labelled as a weak match.",
            "The threshold was calibrated against a real Eurocode part: "
            "genuine on-topic questions scored 60-68%, while questions about "
            "a completely different standard peaked at 44%.",
        ]),
        ("Searching one document or all of them", [
            "The dropdown switches between a single standard and All Loaded "
            "Documents. Use one standard when you know where the answer "
            "lives, and all of them when you do not.",
        ]),
        ("Why there are no calculations", [
            "This app will never solve an equation, substitute a value, or "
            "tell you whether a section passes. It points at the clause and "
            "shows you what it says.",
            "That is a deliberate limit, not a missing feature. A tool that "
            "silently did the arithmetic would put its answer between you "
            "and the code, and the engineering responsibility is yours. "
            "The app's job is to get you to the right page faster.",
        ]),
    ],
    "Flowchart": [
        ("What it is for", [
            "The Flowchart Builder records the sequence you follow for a "
            "design check - which clause you consult, what you decide, and "
            "where you go next. It is a shareable version of the process "
            "that would otherwise live in your head.",
            "It is organisational only. The app never evaluates a decision "
            "or works out which branch you should take.",
        ]),
        ("Building nodes", [
            "+ Step is an ordinary action. + Decision is a fork you write in "
            "your own words ('Is the pile slender?'). + Start and + End mark "
            "the ends of the sequence.",
            "Each node holds a title, free-text notes, an optional link to a "
            "page in one of your PDFs, and an optional equation.",
            "Double-click a node to edit it. Click the blue page reference "
            "on a node to open that exact page.",
        ]),
        ("Connecting them", [
            "Turn on Connect mode, click the node the arrow starts from, "
            "then the node it points to.",
            "Arrows leaving a Decision ask for a caption - usually Yes or "
            "No. Any arrow can be labelled later: right-click it, or "
            "double-click it, and the caption is yours to write. Captions "
            "are for whoever reads the chart; the app never tests them.",
        ]),
        ("Moving around the sheet", [
            "Drag a node to move it. Drag the empty background to pan the "
            "whole sheet. Ctrl + mouse wheel zooms, and clicking the "
            "percentage in the toolbar puts it back to 100%.",
            "Delete removes whichever node or arrow is selected. Deleting a "
            "node takes its arrows with it.",
        ]),
        ("Sending a search result straight to a node", [
            "This is the quickest way to build a chart. Search for what you "
            "need, then click '+ Add to Flowchart' on the result.",
            "The app switches to the Flowchart tab and creates a Step "
            "already carrying the document, the page, the clause number, and "
            "the snippet copied word for word into the notes. Nothing is "
            "retyped, and nothing is summarised on the way across.",
        ]),
        ("Saving your work", [
            "Save and Save As write the chart to a .json file you can keep "
            "beside the job or email to a colleague. Open reloads one.",
            "A workspace goes further: File > Save Workspace records which "
            "PDFs were loaded and the chart you were working on, so you can "
            "return to a whole project state later. The app reopens your "
            "last session automatically, but it only ever writes to a saved "
            "workspace when you ask it to.",
        ]),
    ],
    "Equations": [
        ("The global library", [
            "The equation library holds the expressions you use often, typed "
            "once and available in every workflow from then on.",
            "Open it from the menu: Equations > Manage Global Equations. It "
            "works on its own - you can sit down and type out your standard "
            "expressions before loading a single PDF or drawing a single "
            "node.",
        ]),
        ("Building an equation", [
            "Type the expression in LaTeX, or build it with the symbol "
            "buttons so you do not have to remember the codes. The Greek, "
            "Operators, Relations and Text tabs insert the right code at the "
            "cursor, landing it inside the braces ready for you to type.",
            "The preview underneath redraws as you go, so you can see the "
            "formula rather than the markup. If it will not draw, the reason "
            "is shown in plain English - an unfinished expression or an "
            "unknown command.",
            "Give it a name and click Save to library. Naming it is what "
            "makes it reusable; an equation with a broken expression is "
            "never saved.",
        ]),
        ("Putting one on a node", [
            "Open a node for editing and use the Equation dropdown to pick "
            "one from the library, or Build / edit to write a new one on the "
            "spot. The node grows to make room and draws the formula "
            "properly typeset.",
            "The node keeps its own copy of the expression, so a chart you "
            "send to a colleague still draws correctly on a machine whose "
            "library has never seen it.",
        ]),
        ("What equations are for - and what they are not", [
            "An equation on a node is a picture of a formula. It tells "
            "whoever reads the chart which expression applies at that step.",
            "The app never evaluates it, never substitutes a value into it, "
            "and never produces a result. There is nowhere in the app to "
            "even put a number. The arithmetic, and the responsibility for "
            "it, stay with you.",
        ]),
    ],
}

TAB_ORDER = ("Getting started", "Search", "Flowchart", "Equations")


class GuideDialog(ctk.CTkToplevel):
    """How to drive the app, one tab per feature."""

    def __init__(self, master) -> None:
        super().__init__(master)

        self.title(f"How to use {APP_NAME}")
        self.geometry("760x680")
        self.minsize(620, 560)

        self._build_layout()

        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Escape>", lambda _e: self._close())

        self.transient(master)
        self.after(80, self._focus)

    def _focus(self) -> None:
        try:
            self.grab_set()
            self.lift()
            self.close_button.focus_set()
        except Exception:
            pass

    def _build_layout(self) -> None:
        self.scrollers = []
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            self, text=f"How to use {APP_NAME}", anchor="w",
            font=ctk.CTkFont(size=20, weight="bold"), text_color=ACCENT,
        ).grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 8))

        self.tabs = ctk.CTkTabview(self, corner_radius=8)
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 6))
        for name in TAB_ORDER:
            self.tabs.add(name)
            tab = self.tabs.tab(name)
            tab.grid_columnconfigure(0, weight=1)
            tab.grid_rowconfigure(0, weight=1)
            self._fill(tab, GUIDE[name])
        self.tabs.set(TAB_ORDER[0])

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=20, pady=(4, 16))
        footer.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            footer, text="  " + DISCLAIMER + "  ", anchor="w",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#3d2f00", fg_color=WARNING, corner_radius=6,
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            footer, text=NOT_AFFILIATED, anchor="w", text_color=MUTED,
            font=ctk.CTkFont(size=11), wraplength=520,
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        self.close_button = ctk.CTkButton(
            footer, text="Close", width=110, height=36,
            font=ctk.CTkFont(size=13, weight="bold"), command=self._close,
        )
        self.close_button.grid(row=0, column=1, rowspan=2, sticky="e")

    def _fill(self, tab, sections: List[Section]) -> None:
        body = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        body.grid(row=0, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)

        row = 0
        for heading, paragraphs in sections:
            ctk.CTkLabel(
                body, text=heading, anchor="w", justify="left",
                font=ctk.CTkFont(size=14, weight="bold"),
            ).grid(row=row, column=0, sticky="ew", pady=(14 if row else 4, 4))
            row += 1
            for paragraph in paragraphs:
                ctk.CTkLabel(
                    body, text=paragraph, anchor="w", justify="left",
                    font=ctk.CTkFont(size=12), wraplength=640,
                ).grid(row=row, column=0, sticky="ew", pady=(0, 6))
                row += 1

        self.scrollers.append(smooth_scroll(body))

    def _close(self) -> None:
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()


def show_guide(master) -> None:
    """Open the user guide modally."""
    dialog = GuideDialog(master)
    master.wait_window(dialog)
