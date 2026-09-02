"""Shared UI services: background work and the page-preview lifecycle.

Both the Search tab and the Flowchart Builder need the same two things:

    AsyncRunner     run blocking work off the Tk thread, resume on it
    PreviewManager  open one PDF page in the built-in read-only preview

Keeping them here means a flowchart node opens a clause through exactly the
same code path as a search result - one preview window, one relocation flow,
one set of fallbacks.
"""

from __future__ import annotations

import queue
import threading
import traceback
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Callable, Optional

from .preview_window import DISCLAIMER, PagePreviewWindow, open_in_system_viewer

PUMP_INTERVAL_MS = 40             # how often the UI drains worker results

# A toolbar carries more controls than a narrow window can show side by side.
# Rather than let a button clip silently off the edge, the right-hand group
# drops onto its own line. Used by the search toolbar, the flowchart toolbar
# and the workspace bar.
REFLOW_GUTTER = 24


def reflow_row(row, left, right, wrapped: bool) -> bool:
    """Lay a two-group row out on one line, or two if it will not fit.

    ``row`` must have column 0 stretchy, with ``left`` at (0, 0) and ``right``
    at (0, 1). Returns the new wrapped state, which the caller stores and
    passes back next time - the early return on an unchanged state is what
    stops the re-grid from retriggering <Configure> forever.
    """
    available = row.winfo_width()
    needed = left.winfo_reqwidth() + right.winfo_reqwidth() + REFLOW_GUTTER
    wrap = available > 1 and needed > available
    if wrap == wrapped:
        return wrapped
    if wrap:
        right.grid_configure(row=1, column=0, sticky="w", pady=(8, 0))
    else:
        right.grid_configure(row=0, column=1, sticky="e", pady=0)
    return wrap



class AsyncRunner:
    """Marshals worker-thread results back onto the Tk main thread.

    Tkinter is not thread-safe: worker threads never touch widgets or call
    after(). They post callbacks onto a queue, and the main thread drains it
    on a timer.
    """

    def __init__(self, widget, on_error: Optional[Callable[[Exception], None]] = None):
        self._widget = widget
        self._events: "queue.Queue[tuple]" = queue.Queue()
        self._job: Optional[str] = None
        self._stopped = False
        self.on_error = on_error

    def start(self) -> None:
        self._pump()

    def stop(self) -> None:
        self._stopped = True
        if self._job is not None:
            try:
                self._widget.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def _pump(self) -> None:
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
        if not self._stopped:
            self._job = self._widget.after(PUMP_INTERVAL_MS, self._pump)

    def post(self, callback: Callable, *args) -> None:
        """Hand a callback to the main thread. Safe from any thread."""
        self._events.put((callback, args))

    def run(
        self,
        work: Callable[[], object],
        on_done: Callable[[object], None],
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """Run blocking work off the UI thread, resume on the UI thread."""

        handler = on_error or self.on_error or self._reraise

        def runner() -> None:
            try:
                result = work()
            except Exception as exc:            # surfaced to the user by the
                traceback.print_exc()           # caller's error handler
                self.post(handler, exc)
            else:
                self.post(on_done, result)

        threading.Thread(target=runner, daemon=True).start()

    @staticmethod
    def _reraise(exc: Exception) -> None:
        traceback.print_exception(type(exc), exc, exc.__traceback__)


class PreviewManager:
    """Owns the single page-preview window shared by the whole app.

    Re-points the existing window when the same PDF is asked for again, so the
    engineer never ends up with a stack of preview windows.
    """

    def __init__(
        self,
        master,
        indexer,
        on_status: Optional[Callable[[str], None]] = None,
        on_relocated: Optional[Callable[[int], None]] = None,
    ) -> None:
        self.master = master
        self.indexer = indexer
        self.on_status = on_status or (lambda _text: None)
        self.on_relocated = on_relocated or (lambda _doc_id: None)
        self.window: Optional[PagePreviewWindow] = None

    def open(
        self,
        pdf_path: Path,
        page_number: int,
        label: str = "",
        document_id: Optional[int] = None,
    ) -> None:
        """Show one page of one PDF. Never writes to the engineer's file."""
        pdf_path = Path(pdf_path)

        if not pdf_path.is_file():
            if messagebox.askyesno(
                "PDF not found",
                f"The PDF is no longer at:\n{pdf_path}\n\nLocate it now?",
                parent=self.master,
            ):
                self._relocate(document_id)
            return

        try:
            if self.window is not None and self.window.winfo_exists():
                if Path(self.window.pdf_path) == pdf_path:
                    self.window.go_to_page(page_number)
                    return
                self.window.destroy()

            self.window = PagePreviewWindow(
                self.master, pdf_path=pdf_path, page_number=page_number,
                location_label=label,
            )
            if label:
                self.on_status(f"Opened {label}. {DISCLAIMER}")
        except Exception as exc:
            # Preview failed - fall back to the system viewer.
            traceback.print_exc()
            if messagebox.askyesno(
                "Preview unavailable",
                f"Could not render the page:\n{exc}\n\n"
                "Open the PDF in your default viewer instead?",
                parent=self.master,
            ):
                open_in_system_viewer(pdf_path, page_number)

    def _relocate(self, document_id: Optional[int]) -> None:
        path = filedialog.askopenfilename(
            title="Locate the PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if not path:
            return
        if document_id is not None:
            self.indexer.store.update_file_path(document_id, Path(path))
            self.on_relocated(document_id)
        self.on_status("Path updated. Search again to open it.")

    def close(self) -> None:
        if self.window is not None and self.window.winfo_exists():
            self.window.destroy()
        self.window = None
