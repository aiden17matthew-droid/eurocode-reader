"""Application shell for the Eurocode Reader.

Holds the persistent header (title + liability notice), the tab view, and the
status bar. The tabs themselves are self-contained views:

    SearchView      Phase 1 - load a PDF, index it offline, find the clause
    FlowchartView   Phase 2 - build design workflows that point at clauses

Both share one Indexer, one AsyncRunner and one PreviewManager, so a clause
opens the same way whichever tab asked for it.

The app is an index/compass. It points at clauses, tables and pages; it never
calculates, interprets or suggests design changes.
"""

from __future__ import annotations

from tkinter import messagebox
from typing import Optional

import customtkinter as ctk

from backend.indexer import DISCLAIMER, Indexer, SearchHit

from .flowchart_view import FlowchartView
from .search_view import SearchView
from .services import AsyncRunner, PreviewManager

TAB_SEARCH = "Search"
TAB_FLOWCHART = "Flowchart Builder"

ACCENT = "#3b8ed0"
WARNING = "#e0a800"
MUTED = "#8a8a8a"


class EurocodeReaderApp(ctk.CTk):
    def __init__(self, indexer: Optional[Indexer] = None) -> None:
        super().__init__()

        self.indexer = indexer or Indexer()

        self.title("Eurocode Reader - offline clause finder")
        self.geometry("980x820")
        self.minsize(760, 600)

        self.runner = AsyncRunner(self, on_error=self._default_error)
        self.preview = PreviewManager(
            self,
            indexer=self.indexer,
            on_status=self.set_status,
            # The search tab owns the document list, so a relocated PDF has to
            # be reflected there.
            on_relocated=lambda doc_id: self.search_view.refresh_document_list(
                select_id=doc_id
            ),
        )

        self._build_layout()
        self.runner.start()
        self._warm_up_model()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Configure>", self._on_resize)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # --- header (persistent across every tab) -----------------------
        header = ctk.CTkFrame(self, corner_radius=0, fg_color=("#e8e8e8", "#212121"))
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header, text="Eurocode Reader",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(14, 0))

        ctk.CTkLabel(
            header,
            text="Search your own Eurocode PDFs offline. "
                 "Results point to a page and clause - nothing more.",
            font=ctk.CTkFont(size=12), text_color=MUTED, anchor="w",
        ).grid(row=1, column=0, sticky="w", padx=20, pady=(0, 4))

        # Liability notice - above the tabs, so it is visible on all of them,
        # always visible, never dismissible.
        ctk.CTkLabel(
            header, text="  " + DISCLAIMER + "  ",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#3d2f00", fg_color=WARNING, corner_radius=6,
        ).grid(row=2, column=0, sticky="w", padx=20, pady=(0, 14))

        # --- tabs -------------------------------------------------------
        self.tabs = ctk.CTkTabview(self, corner_radius=8)
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=14, pady=(10, 6))
        self.tabs.add(TAB_SEARCH)
        self.tabs.add(TAB_FLOWCHART)

        for name in (TAB_SEARCH, TAB_FLOWCHART):
            tab = self.tabs.tab(name)
            tab.grid_columnconfigure(0, weight=1)
            tab.grid_rowconfigure(0, weight=1)

        self.search_view = SearchView(
            self.tabs.tab(TAB_SEARCH),
            indexer=self.indexer, runner=self.runner,
            preview=self.preview, set_status=self.set_status,
            on_add_to_flowchart=self.add_hit_to_flowchart,
        )
        self.search_view.grid(row=0, column=0, sticky="nsew")

        self.flowchart_view = FlowchartView(
            self.tabs.tab(TAB_FLOWCHART),
            indexer=self.indexer, runner=self.runner,
            preview=self.preview, set_status=self.set_status,
        )
        self.flowchart_view.grid(row=0, column=0, sticky="nsew")

        self.tabs.set(TAB_SEARCH)

        # --- status bar -------------------------------------------------
        self.status_label = ctk.CTkLabel(
            self, text="Ready.", font=ctk.CTkFont(size=11),
            text_color=MUTED, anchor="w",
        )
        self.status_label.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 10))

    def set_status(self, text: str) -> None:
        self.status_label.configure(text=text)

    # ------------------------------------------------------------------
    # Cross-tab actions
    # ------------------------------------------------------------------
    def add_hit_to_flowchart(self, hit: SearchHit) -> None:
        """Search result -> flowchart step, switching tabs on the way.

        The shell owns both tabs, so this is where the two are joined rather
        than either view reaching into the other.
        """
        self.tabs.set(TAB_FLOWCHART)
        self.flowchart_view.add_node_from_hit(hit)

    def _default_error(self, exc: Exception) -> None:
        self.set_status(f"Error: {exc}")
        messagebox.showerror("Eurocode Reader", str(exc), parent=self)

    # ------------------------------------------------------------------
    # Model warm-up
    # ------------------------------------------------------------------
    def _warm_up_model(self) -> None:
        """Load the local model in the background so the first search is fast."""
        self.set_status("Loading local AI model...")

        self.runner.run(
            work=lambda: self.indexer.embedder.warm_up(),
            on_done=lambda _r: self.set_status(
                "Local model ready. Offline - no internet required."
            ),
            on_error=lambda exc: self.set_status(f"Model not available: {exc}"),
        )

    # ------------------------------------------------------------------
    # Window events
    # ------------------------------------------------------------------
    def _on_resize(self, event) -> None:
        if event.widget is not self:
            return
        self.search_view.on_resize()
        self.flowchart_view.on_resize()

    def _on_close(self) -> None:
        self.runner.stop()
        self.preview.close()
        self.indexer.close()
        self.destroy()
