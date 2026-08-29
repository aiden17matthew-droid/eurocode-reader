"""Read-only page preview, rendered locally with PyMuPDF.

Opens the exact page a search result points to. The page is rasterised to an
image - it is a look-up view, not an editor, and nothing here is written back
to the engineer's PDF.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from typing import Optional

import customtkinter as ctk
from PIL import Image, ImageTk

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover - older PyMuPDF releases
    import fitz

DISCLAIMER = "For navigation only. Verify all clauses in the official Eurocode."

MIN_ZOOM = 0.5
MAX_ZOOM = 4.0
ZOOM_STEP = 0.25
BASE_DPI_SCALE = 2.0      # render at 2x for a crisp image on modern displays


def open_in_system_viewer(pdf_path: Path, page_number: int = 1) -> None:
    """Hand the PDF to the OS default viewer.

    Most viewers cannot be told which page to open from the command line, so
    the in-app preview remains the reliable way to land on an exact page.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF no longer at: {pdf_path}")

    if sys.platform == "win32":
        os.startfile(str(pdf_path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(pdf_path)])
    else:
        subprocess.Popen(["xdg-open", str(pdf_path)])


class PagePreviewWindow(ctk.CTkToplevel):
    """A scrollable, read-only render of one PDF page."""

    def __init__(
        self,
        master,
        pdf_path: Path,
        page_number: int,
        location_label: str = "",
    ) -> None:
        super().__init__(master)

        self.pdf_path = Path(pdf_path)
        self.page_number = page_number          # 1-based
        self.zoom = 1.0
        self._photo: Optional[ImageTk.PhotoImage] = None
        self._doc = None

        self.title(f"{self.pdf_path.name} - page {page_number}")
        self.geometry("900x1000")
        self.minsize(500, 400)

        try:
            self._doc = fitz.open(self.pdf_path)
        except Exception as exc:
            self._show_error(f"Could not open the PDF:\n{exc}")
            return

        self.total_pages = self._doc.page_count
        self.page_number = max(1, min(page_number, self.total_pages))

        self._build_layout(location_label)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Escape>", lambda _e: self._on_close())
        self.bind("<Prior>", lambda _e: self._step_page(-1))   # PageUp
        self.bind("<Next>", lambda _e: self._step_page(1))     # PageDown

        # Render once the window has a real width to fit to.
        self.after(60, self._fit_to_width)

        self.transient(master)
        self.lift()
        self.focus_force()

    # --- layout ------------------------------------------------------------
    def _build_layout(self, location_label: str) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        toolbar = ctk.CTkFrame(self, corner_radius=0)
        toolbar.grid(row=0, column=0, sticky="ew")

        ctk.CTkButton(
            toolbar, text="< Prev", width=70,
            command=lambda: self._step_page(-1),
        ).pack(side="left", padx=(10, 4), pady=8)

        self.page_label = ctk.CTkLabel(toolbar, text="", width=120)
        self.page_label.pack(side="left", padx=4)

        ctk.CTkButton(
            toolbar, text="Next >", width=70,
            command=lambda: self._step_page(1),
        ).pack(side="left", padx=4, pady=8)

        ctk.CTkButton(
            toolbar, text="-", width=36,
            command=lambda: self._change_zoom(-ZOOM_STEP),
        ).pack(side="left", padx=(20, 2), pady=8)
        ctk.CTkButton(
            toolbar, text="+", width=36,
            command=lambda: self._change_zoom(ZOOM_STEP),
        ).pack(side="left", padx=2, pady=8)
        ctk.CTkButton(
            toolbar, text="Fit width", width=80, command=self._fit_to_width,
        ).pack(side="left", padx=(2, 10), pady=8)

        ctk.CTkButton(
            toolbar, text="Open in system viewer", width=170,
            command=self._open_externally,
        ).pack(side="right", padx=10, pady=8)

        if location_label:
            ctk.CTkLabel(
                toolbar, text=location_label,
                font=ctk.CTkFont(size=12, weight="bold"),
            ).pack(side="right", padx=10)

        # Canvas + scrollbars for the rendered page.
        canvas_frame = ctk.CTkFrame(self, corner_radius=0)
        canvas_frame.grid(row=1, column=0, sticky="nsew")
        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            canvas_frame, background="#3a3a3a", highlightthickness=0,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")

        v_scroll = ctk.CTkScrollbar(
            canvas_frame, orientation="vertical", command=self.canvas.yview,
        )
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll = ctk.CTkScrollbar(
            canvas_frame, orientation="horizontal", command=self.canvas.xview,
        )
        h_scroll.grid(row=1, column=0, sticky="ew")
        self.canvas.configure(
            yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set,
        )

        # Mouse wheel scrolling (Windows / macOS / Linux button events).
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", lambda _e: self.canvas.yview_scroll(-3, "units"))
        self.canvas.bind_all("<Button-5>", lambda _e: self.canvas.yview_scroll(3, "units"))

        ctk.CTkLabel(
            self, text=DISCLAIMER,
            font=ctk.CTkFont(size=11), text_color="#e0a800",
        ).grid(row=2, column=0, pady=6)

    def _show_error(self, message: str) -> None:
        ctk.CTkLabel(self, text=message, wraplength=420).pack(
            padx=30, pady=30, expand=True
        )

    # --- rendering ---------------------------------------------------------
    def _render(self) -> None:
        if self._doc is None:
            return
        page = self._doc.load_page(self.page_number - 1)
        matrix = fitz.Matrix(self.zoom * BASE_DPI_SCALE,
                             self.zoom * BASE_DPI_SCALE)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)

        image = Image.frombytes(
            "RGB", (pixmap.width, pixmap.height), pixmap.samples
        )
        # Keep a reference on self, or Tk garbage-collects the image.
        self._photo = ImageTk.PhotoImage(image)

        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self._photo)
        self.canvas.configure(scrollregion=(0, 0, pixmap.width, pixmap.height))
        self.canvas.yview_moveto(0)

        self.page_label.configure(
            text=f"Page {self.page_number} / {self.total_pages}"
        )
        self.title(f"{self.pdf_path.name} - page {self.page_number}")

    def _fit_to_width(self) -> None:
        """Scale so the page width matches the visible canvas width."""
        if self._doc is None:
            return
        self.update_idletasks()
        available = self.canvas.winfo_width()
        if available <= 1:
            self.after(60, self._fit_to_width)
            return
        page_width = self._doc.load_page(self.page_number - 1).rect.width
        if page_width <= 0:
            return
        self.zoom = max(
            MIN_ZOOM,
            min(MAX_ZOOM, (available - 24) / (page_width * BASE_DPI_SCALE)),
        )
        self._render()

    def _change_zoom(self, delta: float) -> None:
        new_zoom = round(min(MAX_ZOOM, max(MIN_ZOOM, self.zoom + delta)), 2)
        if new_zoom != self.zoom:
            self.zoom = new_zoom
            self._render()

    def _step_page(self, delta: int) -> None:
        target = self.page_number + delta
        if 1 <= target <= self.total_pages:
            self.page_number = target
            self._render()

    def go_to_page(self, page_number: int) -> None:
        """Re-point an already-open preview at a different page."""
        self.page_number = max(1, min(page_number, self.total_pages))
        self._render()
        self.lift()
        self.focus_force()

    # --- events ------------------------------------------------------------
    def _on_mousewheel(self, event) -> None:
        self.canvas.yview_scroll(int(-event.delta / 60), "units")

    def _open_externally(self) -> None:
        try:
            open_in_system_viewer(self.pdf_path, self.page_number)
        except Exception as exc:
            self._show_error(str(exc))

    def _on_close(self) -> None:
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")
        if self._doc is not None:
            self._doc.close()
            self._doc = None
        self.destroy()
