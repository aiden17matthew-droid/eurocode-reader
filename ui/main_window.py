"""Main CustomTkinter window for the Eurocode Reader.

Flow: Load PDF -> one-time offline indexing -> natural-language search ->
click a result -> read-only preview of that exact page.

The app is an index/compass. It points at clauses, tables and pages; it never
calculates, interprets or suggests design changes.
"""

from __future__ import annotations

import queue
import threading
import time
import traceback
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
from .preview_window import PagePreviewWindow, open_in_system_viewer
from .result_card import ResultCard

ALL_DOCUMENTS = "All documents"
PROGRESS_INTERVAL = 0.05          # seconds between UI progress updates
PUMP_INTERVAL_MS = 40             # how often the UI drains worker results
DEFAULT_TOP_K = 5

ACCENT = "#3b8ed0"
WARNING = "#e0a800"
MUTED = "#8a8a8a"


class EurocodeReaderApp(ctk.CTk):
    def __init__(self, indexer: Optional[Indexer] = None) -> None:
        super().__init__()

        self.indexer = indexer or Indexer()
        self.preview: Optional[PagePreviewWindow] = None
        self.cards: List[ResultCard] = []
        self.doc_labels: Dict[str, Optional[int]] = {ALL_DOCUMENTS: None}
        self.busy = False
        self._last_progress = 0.0

        # Tkinter is not thread-safe: worker threads never touch widgets or
        # call after(). They post callbacks here, and the main thread drains
        # the queue on a timer.
        self._events: "queue.Queue[tuple]" = queue.Queue()
        self._pump_job: Optional[str] = None
        self._closing = False

        self.title("Eurocode Reader - offline clause finder")
        self.geometry("980x820")
        self.minsize(760, 600)

        self._build_layout()
        self._refresh_document_list()
        self._pump_events()
        self._warm_up_model()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Configure>", self._on_resize)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        # --- header -----------------------------------------------------
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

        # Liability notice - always visible, never dismissible.
        ctk.CTkLabel(
            header, text="  " + DISCLAIMER + "  ",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#3d2f00", fg_color=WARNING, corner_radius=6,
        ).grid(row=2, column=0, sticky="w", padx=20, pady=(0, 14))

        # --- toolbar ----------------------------------------------------
        toolbar = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        toolbar.grid(row=1, column=0, sticky="ew", padx=20, pady=(14, 0))
        toolbar.grid_columnconfigure(3, weight=1)

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

        self.remove_button = ctk.CTkButton(
            toolbar, text="Remove from index", width=150, height=34,
            fg_color="transparent", border_width=1, text_color=MUTED,
            command=self._on_remove_document,
        )
        self.remove_button.grid(row=0, column=4, sticky="e")

        # --- progress ---------------------------------------------------
        self.progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.progress_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=(10, 0))
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
        search_row.grid(row=3, column=0, sticky="ew", padx=20, pady=(14, 6))
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
        self.results_frame.grid(row=4, column=0, sticky="nsew", padx=20, pady=6)
        self.results_frame.grid_columnconfigure(0, weight=1)

        self.placeholder = ctk.CTkLabel(
            self.results_frame,
            text="Load a Eurocode PDF to begin.",
            font=ctk.CTkFont(size=13), text_color=MUTED,
            justify="center", wraplength=520,
        )
        self.placeholder.grid(row=0, column=0, pady=40)

        # --- status bar -------------------------------------------------
        self.status_label = ctk.CTkLabel(
            self, text="Ready.", font=ctk.CTkFont(size=11),
            text_color=MUTED, anchor="w",
        )
        self.status_label.grid(row=5, column=0, sticky="ew", padx=20, pady=(0, 10))

    # ------------------------------------------------------------------
    # Threading helpers
    # ------------------------------------------------------------------
    def _pump_events(self) -> None:
        """Main-thread timer: run callbacks posted by worker threads."""
        while True:
            try:
                callback, args = self._events.get_nowait()
            except queue.Empty:
                break
            try:
                callback(*args)
            except Exception:                   # a broken callback must not
                traceback.print_exc()           # kill the pump
        if not self._closing:
            self._pump_job = self.after(PUMP_INTERVAL_MS, self._pump_events)

    def _post(self, callback: Callable, *args) -> None:
        """Hand a callback to the main thread. Safe from any thread."""
        self._events.put((callback, args))

    def _run_async(
        self,
        work: Callable[[], object],
        on_done: Callable[[object], None],
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """Run blocking work off the UI thread, resume on the UI thread."""

        def runner() -> None:
            try:
                result = work()
            except Exception as exc:            # surfaced to the user below
                traceback.print_exc()
                self._post(on_error or self._default_error, exc)
            else:
                self._post(on_done, result)

        threading.Thread(target=runner, daemon=True).start()

    def _default_error(self, exc: Exception) -> None:
        self._set_busy(False)
        self._hide_progress()
        self.status_label.configure(text=f"Error: {exc}")
        messagebox.showerror("Eurocode Reader", str(exc), parent=self)

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        state = "disabled" if busy else "normal"
        self.load_button.configure(state=state)
        self.search_button.configure(state=state)
        self.remove_button.configure(state=state)

    # ------------------------------------------------------------------
    # Model warm-up
    # ------------------------------------------------------------------
    def _warm_up_model(self) -> None:
        """Load the local model in the background so the first search is fast."""
        self.status_label.configure(text="Loading local AI model...")

        self._run_async(
            work=lambda: self.indexer.embedder.warm_up(),
            on_done=lambda _r: self.status_label.configure(
                text="Local model ready. Offline - no internet required."
            ),
            on_error=lambda exc: self.status_label.configure(
                text=f"Model not available: {exc}"
            ),
        )

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
            self._post(self._update_progress, fraction, text)

        self._run_async(
            work=lambda: self.indexer.index_pdf(pdf_path, progress=on_progress),
            on_done=self._on_index_done,
        )

    def _on_index_done(self, result: object) -> None:
        assert isinstance(result, IndexResult)
        self._set_busy(False)
        self._hide_progress()
        self._refresh_document_list(select_id=result.document_id)

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
        self.status_label.configure(text=message)

        self._clear_results()
        self.placeholder.configure(
            text="Type a query above to find the relevant clause."
        )
        self.placeholder.grid()
        self.search_entry.focus_set()

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

    # ------------------------------------------------------------------
    # Document library
    # ------------------------------------------------------------------
    def _refresh_document_list(self, select_id: Optional[int] = None) -> None:
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
        self._refresh_document_list()
        self._clear_results()
        self.placeholder.grid()
        self.status_label.configure(text=f"Removed '{label}' from the index.")

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
        self.status_label.configure(text="Searching locally...")

        self._run_async(
            work=lambda: self.indexer.search(
                query, top_k=DEFAULT_TOP_K, document_id=doc_id
            ),
            on_done=lambda hits: self._render_results(hits, query),
        )

    def _render_results(self, hits: object, query: str) -> None:
        assert isinstance(hits, list)
        self._set_busy(False)
        self._clear_results()

        if not hits:
            self.placeholder.configure(
                text="No matches found. Try different wording, "
                     "or check the document filter."
            )
            self.placeholder.grid()
            self.status_label.configure(text=f"No matches for '{query}'.")
            return

        # A weak match is a false pointer. Below the relevance floor, say so
        # plainly rather than sending the engineer to an unrelated page.
        relevant = [hit for hit in hits if hit.score >= MIN_RELEVANCE]

        if not relevant:
            best = max(hit.score for hit in hits)
            self.placeholder.configure(
                text=(
                    "No relevant clauses found in this document.\n"
                    f"(Highest match was only {best:.0%}, "
                    f"below the {MIN_RELEVANCE:.0%} relevance threshold.)\n\n"
                    "Try loading a different Eurocode part."
                )
            )
            self.placeholder.grid()
            self.status_label.configure(
                text=f"Nothing relevant for '{query}' "
                     f"(best match {best:.0%})."
            )
            return

        self.placeholder.grid_remove()
        width = self.results_frame.winfo_width()

        for rank, hit in enumerate(relevant, start=1):
            card = ResultCard(
                self.results_frame, hit=hit, rank=rank, on_open=self._open_hit,
            )
            card.grid(row=rank - 1, column=0, sticky="ew", padx=6, pady=6)
            if width > 1:
                card.set_wraplength(width)
            self.cards.append(card)

        hidden = len(hits) - len(relevant)
        suffix = f" ({hidden} weak match(es) hidden)" if hidden else ""
        self.status_label.configure(
            text=f"{len(relevant)} location(s) for '{query}'{suffix}. "
                 f"{DISCLAIMER}"
        )

    def _clear_results(self) -> None:
        for card in self.cards:
            card.destroy()
        self.cards.clear()

    # ------------------------------------------------------------------
    # Opening a result
    # ------------------------------------------------------------------
    def _open_hit(self, hit: SearchHit) -> None:
        pdf_path = Path(hit.document_path)
        if not pdf_path.is_file():
            if messagebox.askyesno(
                "PDF not found",
                f"The PDF is no longer at:\n{pdf_path}\n\n"
                "Locate it now?",
                parent=self,
            ):
                self._relocate_pdf(hit)
            return

        try:
            if self.preview is not None and self.preview.winfo_exists():
                if Path(self.preview.pdf_path) == pdf_path:
                    self.preview.go_to_page(hit.page_number)
                    return
                self.preview.destroy()

            self.preview = PagePreviewWindow(
                self, pdf_path=pdf_path, page_number=hit.page_number,
                location_label=hit.location_label,
            )
            self.status_label.configure(
                text=f"Opened {hit.location_label}. {DISCLAIMER}"
            )
        except Exception as exc:
            # Preview failed - fall back to the system viewer.
            traceback.print_exc()
            if messagebox.askyesno(
                "Preview unavailable",
                f"Could not render the page:\n{exc}\n\n"
                "Open the PDF in your default viewer instead?",
                parent=self,
            ):
                open_in_system_viewer(pdf_path, hit.page_number)

    def _relocate_pdf(self, hit: SearchHit) -> None:
        path = filedialog.askopenfilename(
            title="Locate the PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if not path:
            return
        self.indexer.store.update_file_path(hit.document_id, Path(path))
        self._refresh_document_list(select_id=hit.document_id)
        self.status_label.configure(
            text="Path updated. Search again to open it."
        )

    # ------------------------------------------------------------------
    # Window events
    # ------------------------------------------------------------------
    def _on_resize(self, event) -> None:
        if event.widget is not self:
            return
        width = self.results_frame.winfo_width()
        if width > 1:
            for card in self.cards:
                card.set_wraplength(width)

    def _on_close(self) -> None:
        self._closing = True
        if self._pump_job is not None:
            try:
                self.after_cancel(self._pump_job)
            except Exception:
                pass
            self._pump_job = None
        if self.preview is not None and self.preview.winfo_exists():
            self.preview.destroy()
        self.indexer.close()
        self.destroy()
