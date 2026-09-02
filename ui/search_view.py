"""The Search tab: load a PDF, index it offline, find the clause.

This is Phase 1's interface, unchanged in behaviour - only lifted out of the
main window so it can sit alongside the Flowchart Builder in a tab view.

The app is an index/compass. It points at clauses, tables and pages; it never
calculates, interprets or suggests design changes.
"""

from __future__ import annotations

import time
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Callable, Dict, List, Optional

import customtkinter as ctk

from backend.indexer import (
    DISCLAIMER,
    MIN_RELEVANCE,
    Indexer,
    IndexResult,
    SearchHit,
)

from .result_card import ResultCard
from .services import AsyncRunner, PreviewManager, reflow_row

ALL_DOCUMENTS = "All Loaded Documents"
PROGRESS_INTERVAL = 0.05          # seconds between UI progress updates
DEFAULT_TOP_K = 5

MUTED = "#8a8a8a"


class SearchView(ctk.CTkFrame):
    """Natural-language lookup over the locally indexed Eurocode PDFs."""

    def __init__(
        self,
        master,
        indexer: Indexer,
        runner: AsyncRunner,
        preview: PreviewManager,
        set_status: Callable[[str], None],
        on_add_to_flowchart: Optional[Callable[[SearchHit], None]] = None,
        on_documents_changed: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(master, fg_color="transparent")

        self.indexer = indexer
        self.runner = runner
        self.preview = preview
        self.set_status = set_status
        # Supplied by the shell, which owns both tabs. Without it the cards
        # simply have no Add button.
        self.on_add_to_flowchart = on_add_to_flowchart
        # Lets the shell know the workspace's document set has moved on.
        self.on_documents_changed = on_documents_changed or (lambda: None)

        self.cards: List[ResultCard] = []
        self.doc_labels: Dict[str, Optional[int]] = {ALL_DOCUMENTS: None}
        self.busy = False
        self._last_progress = 0.0
        # Kept so the weak-match toggle can re-render without re-searching.
        self._last_hits: List[SearchHit] = []
        self._last_query = ""

        self._build_layout()
        self.refresh_document_list()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # --- toolbar ----------------------------------------------------
        # Two groups so the right-hand one can drop to its own line on a
        # narrow window instead of being clipped off the edge.
        self.toolbar = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.toolbar.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 0))
        self.toolbar.grid_columnconfigure(0, weight=1)

        toolbar = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="w")
        self.left_tools = toolbar

        self.right_tools = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        self.right_tools.grid(row=0, column=1, sticky="e")
        self._tools_wrapped = False
        # Reflow on the row's own resize, not just the window's: a tab
        # that was hidden when the window changed size still has to
        # re-measure the first time it is shown.
        self.toolbar.bind(
            "<Configure>",
            lambda _e: self._reflow_tools(),
        )

        self.load_button = ctk.CTkButton(
            toolbar, text="Load PDF", width=110, height=34,
            font=ctk.CTkFont(size=13, weight="bold"), command=self._on_load_pdf,
        )
        self.load_button.grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(toolbar, text="Search in:", text_color=MUTED).grid(
            row=0, column=1, padx=(16, 6)
        )

        self.doc_menu = ctk.CTkOptionMenu(
            toolbar, values=[ALL_DOCUMENTS], width=260, height=34,
            command=lambda _v: None,
        )
        self.doc_menu.grid(row=0, column=2, sticky="w")

        # Off by default: a weak match is usually a false pointer. But the
        # engineer may be hunting for wording the model scores badly, so the
        # floor is a default, not a wall.
        self.weak_check = ctk.CTkCheckBox(
            self.right_tools,
            text=f"Include weak matches (under {MIN_RELEVANCE:.0%})",
            font=ctk.CTkFont(size=12), text_color=MUTED,
            checkbox_width=18, checkbox_height=18,
            command=self._on_weak_toggled,
        )
        self.weak_check.grid(row=0, column=0, sticky="w", padx=(0, 16))

        self.remove_button = ctk.CTkButton(
            self.right_tools, text="Remove from index", width=150, height=34,
            fg_color="transparent", border_width=1, text_color=MUTED,
            command=self._on_remove_document,
        )
        self.remove_button.grid(row=0, column=1, sticky="e")

        # --- progress ---------------------------------------------------
        self.progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.progress_frame.grid(row=1, column=0, sticky="ew", padx=6, pady=(10, 0))
        self.progress_frame.grid_columnconfigure(0, weight=1)

        self.progress_bar = ctk.CTkProgressBar(self.progress_frame, height=10)
        self.progress_bar.grid(row=0, column=0, sticky="ew")
        self.progress_bar.set(0)

        self.progress_label = ctk.CTkLabel(
            self.progress_frame, text="", font=ctk.CTkFont(size=11),
            text_color=MUTED, anchor="w",
        )
        self.progress_label.grid(row=1, column=0, sticky="w", pady=(2, 0))
        self.progress_frame.grid_remove()          # hidden until indexing

        # --- search bar -------------------------------------------------
        search_row = ctk.CTkFrame(self, fg_color="transparent")
        search_row.grid(row=2, column=0, sticky="ew", padx=6, pady=(14, 6))
        search_row.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(
            search_row, height=42, font=ctk.CTkFont(size=14),
            placeholder_text="Describe what you need, "
                             "e.g. 'shear resistance of bored piles'",
        )
        self.search_entry.grid(row=0, column=0, sticky="ew")
        self.search_entry.bind("<Return>", lambda _e: self._on_search())

        self.search_button = ctk.CTkButton(
            search_row, text="Search", width=110, height=42,
            font=ctk.CTkFont(size=13, weight="bold"), command=self._on_search,
        )
        self.search_button.grid(row=0, column=1, padx=(10, 0))

        # --- results ----------------------------------------------------
        self.results_frame = ctk.CTkScrollableFrame(
            self, label_text="Results", corner_radius=8,
        )
        self.results_frame.grid(row=3, column=0, sticky="nsew", padx=6, pady=6)
        self.results_frame.grid_columnconfigure(0, weight=1)

        self.placeholder = ctk.CTkLabel(
            self.results_frame,
            text="Load a Eurocode PDF to begin.",
            font=ctk.CTkFont(size=13), text_color=MUTED,
            justify="center", wraplength=520,
        )
        self.placeholder.grid(row=0, column=0, pady=40)

    # ------------------------------------------------------------------
    # Busy state / errors
    # ------------------------------------------------------------------
    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        state = "disabled" if busy else "normal"
        self.load_button.configure(state=state)
        self.search_button.configure(state=state)
        self.remove_button.configure(state=state)

    def handle_error(self, exc: Exception) -> None:
        self._set_busy(False)
        self._hide_progress()
        self.set_status(f"Error: {exc}")
        messagebox.showerror("Eurocode Reader", str(exc), parent=self)

    # ------------------------------------------------------------------
    # Loading / indexing
    # ------------------------------------------------------------------
    def _on_load_pdf(self) -> None:
        if self.busy:
            return
        path = filedialog.askopenfilename(
            title="Select a Eurocode PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if not path:
            return
        self._index_pdf(Path(path))

    def _index_pdf(self, pdf_path: Path) -> None:
        self._set_busy(True)
        self._show_progress(f"Reading {pdf_path.name}...")
        self._last_progress = 0.0

        def on_progress(stage: str, done: int, total: int) -> None:
            # Called from the worker thread - throttle, then marshal to the UI.
            now = time.monotonic()
            if now - self._last_progress < PROGRESS_INTERVAL and done < total:
                return
            self._last_progress = now
            fraction = done / total if total else 0.0
            text = (
                f"Reading pages: {done}/{total}"
                if stage == "reading"
                else f"Creating local embeddings: {done}/{total} chunks"
            )
            self.runner.post(self._update_progress, fraction, text)

        self.runner.run(
            work=lambda: self.indexer.index_pdf(pdf_path, progress=on_progress),
            on_done=self._on_index_done,
            on_error=self.handle_error,
        )

    def _on_index_done(self, result: object) -> None:
        assert isinstance(result, IndexResult)
        self._set_busy(False)
        self._hide_progress()
        self.refresh_document_list(select_id=result.document_id)

        if result.already_indexed:
            message = (
                f"'{result.title}' was already indexed "
                f"({result.chunk_count} sections). Ready to search."
            )
        else:
            message = (
                f"Indexed '{result.title}': {result.page_count} pages, "
                f"{result.chunk_count} searchable sections."
            )
        self.set_status(message)

        self._forget_results()
        self.placeholder.configure(
            text="Type a query above to find the relevant clause."
        )
        self.placeholder.grid()
        self.search_entry.focus_set()
        self.on_documents_changed()

    def _show_progress(self, text: str) -> None:
        self.progress_frame.grid()
        self.progress_bar.set(0)
        self.progress_label.configure(text=text)

    def _update_progress(self, fraction: float, text: str) -> None:
        self.progress_bar.set(fraction)
        self.progress_label.configure(text=text)

    def _hide_progress(self) -> None:
        self.progress_frame.grid_remove()
        self.progress_bar.set(0)
        self.progress_label.configure(text="")

    def index_documents(
        self,
        paths: List[Path],
        on_done: Callable[[List[str]], None],
    ) -> None:
        """Index several PDFs in one background pass, showing progress.

        Used when a workspace refers to a Eurocode this machine has not
        indexed yet. Failures are collected rather than aborting the rest -
        one unreadable PDF should not cost the engineer the whole workspace.
        """
        if not paths:
            on_done([])
            return

        self._set_busy(True)
        self._show_progress(f"Restoring {len(paths)} document(s)...")
        self._last_progress = 0.0
        total = len(paths)

        def work() -> List[str]:
            problems: List[str] = []
            for position, pdf_path in enumerate(paths, start=1):

                def on_progress(stage: str, done: int, count: int,
                                _p=position, _name=pdf_path.name) -> None:
                    now = time.monotonic()
                    if now - self._last_progress < PROGRESS_INTERVAL and done < count:
                        return
                    self._last_progress = now
                    fraction = ((_p - 1) + (done / count if count else 0)) / total
                    label = "Reading" if stage == "reading" else "Embedding"
                    self.runner.post(
                        self._update_progress, fraction,
                        f"[{_p}/{total}] {label} {_name}: {done}/{count}",
                    )

                try:
                    self.indexer.index_pdf(pdf_path, progress=on_progress)
                except Exception as exc:
                    problems.append(f"{pdf_path.name}: {exc}")
            return problems

        def done(problems: object) -> None:
            self._set_busy(False)
            self._hide_progress()
            self.refresh_document_list()
            on_done(list(problems) if isinstance(problems, list) else [])

        self.runner.run(work=work, on_done=done, on_error=self.handle_error)

    # ------------------------------------------------------------------
    # Document library
    # ------------------------------------------------------------------
    def refresh_document_list(self, select_id: Optional[int] = None) -> None:
        docs = self.indexer.list_documents()
        self.doc_labels = {ALL_DOCUMENTS: None}

        for doc in docs:
            label = f"{doc['title']} ({doc['page_count']} pp)"
            # Guard against two PDFs sharing a title.
            if label in self.doc_labels:
                label = f"{label} [{doc['id']}]"
            self.doc_labels[label] = int(doc["id"])

        values = list(self.doc_labels.keys())
        self.doc_menu.configure(values=values)

        selected = values[0]
        if select_id is not None:
            for label, doc_id in self.doc_labels.items():
                if doc_id == select_id:
                    selected = label
                    break
        self.doc_menu.set(selected)

        if not docs:
            self.placeholder.configure(text="Load a Eurocode PDF to begin.")

    def _selected_document_id(self) -> Optional[int]:
        return self.doc_labels.get(self.doc_menu.get())

    def selected_document_label(self) -> str:
        """What the dropdown is currently pointed at, for status messages."""
        return self.doc_menu.get()

    def selected_document_title(self) -> Optional[str]:
        """Title of the selected document, or None for all documents.

        Saved into the workspace so reopening it puts the engineer back on the
        Eurocode they were reading, not on a reset dropdown.
        """
        doc_id = self._selected_document_id()
        if doc_id is None:
            return None
        for doc in self.indexer.list_documents():
            if int(doc["id"]) == doc_id:
                return str(doc["title"])
        return None

    def _on_remove_document(self) -> None:
        doc_id = self._selected_document_id()
        if doc_id is None:
            messagebox.showinfo(
                "Eurocode Reader",
                "Select a specific document to remove it from the index.",
                parent=self,
            )
            return
        label = self.doc_menu.get()
        if not messagebox.askyesno(
            "Remove from index",
            f"Remove '{label}' from the local index?\n\n"
            "Your PDF file is not touched - only the search index is cleared.",
            parent=self,
        ):
            return
        self.indexer.remove_document(doc_id)
        self.refresh_document_list()
        self._forget_results()
        self.placeholder.grid()
        self.set_status(f"Removed '{label}' from the index.")
        self.on_documents_changed()

    # ------------------------------------------------------------------
    # Searching
    # ------------------------------------------------------------------
    def _on_search(self) -> None:
        if self.busy:
            return
        query = self.search_entry.get().strip()
        if not query:
            return
        if not self.indexer.list_documents():
            messagebox.showinfo(
                "Eurocode Reader",
                "Load a Eurocode PDF first - the index is empty.",
                parent=self,
            )
            return

        doc_id = self._selected_document_id()
        self._set_busy(True)
        self.set_status("Searching locally...")

        self.runner.run(
            work=lambda: self.indexer.search(
                query, top_k=DEFAULT_TOP_K, document_id=doc_id
            ),
            on_done=lambda hits: self._render_results(hits, query),
            on_error=self.handle_error,
        )

    def _on_weak_toggled(self) -> None:
        """Re-render what is already on screen - no need to search again."""
        if self._last_query:
            self._render_results(self._last_hits, self._last_query)
        elif self.weak_check.get():
            self.set_status(
                f"Weak matches (under {MIN_RELEVANCE:.0%}) will be shown, "
                f"clearly marked, on your next search."
            )
        else:
            self.set_status(
                f"Weak matches under {MIN_RELEVANCE:.0%} will be hidden again."
            )

    def _render_results(self, hits: object, query: str) -> None:
        assert isinstance(hits, list)
        self._set_busy(False)
        self._clear_results()
        self._last_hits = hits
        self._last_query = query

        if not hits:
            self.placeholder.configure(
                text="No matches found. Try different wording, "
                     "or check the document filter."
            )
            self.placeholder.grid()
            self.set_status(f"No matches for '{query}'.")
            return

        # A weak match is usually a false pointer, so it is hidden by default.
        # The engineer can ask for them anyway - some searches are for wording
        # the model scores poorly - and every one shown is labelled as weak.
        show_weak = bool(self.weak_check.get())
        relevant = [hit for hit in hits if hit.score >= MIN_RELEVANCE]
        weak = [hit for hit in hits if hit.score < MIN_RELEVANCE]
        display = hits if show_weak else relevant

        if not display:
            best = max(hit.score for hit in hits)
            self.placeholder.configure(
                text=(
                    "No relevant clauses found in this document.\n"
                    f"(Highest match was only {best:.0%}, "
                    f"below the {MIN_RELEVANCE:.0%} relevance threshold.)\n\n"
                    "Try loading a different Eurocode part, or tick "
                    "'Include weak matches' above to see them anyway."
                )
            )
            self.placeholder.grid()
            self.set_status(
                f"Nothing relevant for '{query}' (best match {best:.0%})."
            )
            return

        self.placeholder.grid_remove()
        width = self.results_frame.winfo_width()

        for rank, hit in enumerate(display, start=1):
            card = ResultCard(
                self.results_frame, hit=hit, rank=rank, on_open=self.open_hit,
                weak=hit.score < MIN_RELEVANCE,
                on_add=self.add_hit_to_flowchart
                if self.on_add_to_flowchart else None,
            )
            card.grid(row=rank - 1, column=0, sticky="ew", padx=6, pady=6)
            if width > 1:
                card.set_wraplength(width)
            self.cards.append(card)

        if show_weak and weak:
            suffix = (f" - {len(weak)} of them weak and shown at your request")
        elif weak:
            suffix = f" ({len(weak)} weak match(es) hidden)"
        else:
            suffix = ""
        self.set_status(
            f"{len(display)} location(s) for '{query}'{suffix}. {DISCLAIMER}"
        )

    def _clear_results(self) -> None:
        for card in self.cards:
            card.destroy()
        self.cards.clear()

    def _forget_results(self) -> None:
        """Drop the cached hits too, so the weak-match toggle cannot bring
        back results for a document that is no longer indexed."""
        self._clear_results()
        self._last_hits = []
        self._last_query = ""

    # ------------------------------------------------------------------
    # Opening a result
    # ------------------------------------------------------------------
    def open_hit(self, hit: SearchHit) -> None:
        self.preview.open(
            Path(hit.document_path),
            page_number=hit.page_number,
            label=hit.location_label,
            document_id=hit.document_id,
        )

    def add_hit_to_flowchart(self, hit: SearchHit) -> None:
        """Hand a result to the Flowchart tab - no preview, no retyping."""
        if self.on_add_to_flowchart is not None:
            self.on_add_to_flowchart(hit)

    # ------------------------------------------------------------------
    # Window events
    # ------------------------------------------------------------------
    def on_resize(self) -> None:
        """Re-flow snippet text and the toolbar when the width changes."""
        width = self.results_frame.winfo_width()
        if width > 1:
            for card in self.cards:
                card.set_wraplength(width)
        self._reflow_tools()

    def _reflow_tools(self) -> None:
        self._tools_wrapped = reflow_row(
            self.toolbar, self.left_tools, self.right_tools,
            self._tools_wrapped,
        )

