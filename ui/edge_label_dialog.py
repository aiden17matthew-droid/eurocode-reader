"""Caption a connection between two flowchart nodes.

A label is text the engineer writes for whoever reads the chart - "Yes",
"No", "if the pile is slender". The app stores it and draws it. It never
parses it, never evaluates it, and never decides which branch is taken.
That decision stays with the engineer.

Labels are optional: most sequential steps do not need one, and the dialog
makes leaving it blank a first-class choice rather than a cancel.
"""

from __future__ import annotations

from typing import Optional

import customtkinter as ctk

from backend.flowchart import MAX_LABEL
from backend.indexer import DISCLAIMER

MUTED = "#8a8a8a"
WARNING = "#e0a800"

QUICK_LABELS = ("Yes", "No")


class EdgeLabelDialog(ctk.CTkToplevel):
    """Modal prompt for one connection's caption.

    ``result`` is None if the engineer cancelled, otherwise the new label -
    which may be an empty string, meaning they deliberately want no caption.
    """

    def __init__(
        self,
        master,
        source_title: str,
        target_title: str,
        initial: str = "",
    ) -> None:
        super().__init__(master)

        self.result: Optional[str] = None
        self._initial = initial or ""

        self.title("Label connection")
        self.geometry("520x330")
        self.minsize(440, 300)
        self.resizable(True, False)

        self._build_layout(source_title, target_title)

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.bind("<Escape>", lambda _e: self._on_cancel())
        self.bind("<Return>", lambda _e: self._on_save())

        self.transient(master)
        self.after(80, self._focus_first)

    def _focus_first(self) -> None:
        try:
            self.grab_set()
            self.lift()
            self.entry.focus_set()
            self.entry.select_range(0, "end")
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _build_layout(self, source_title: str, target_title: str) -> None:
        self.grid_columnconfigure(0, weight=1)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=0, column=0, sticky="nsew", padx=18, pady=(16, 0))
        body.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            body, anchor="w", justify="left",
            font=ctk.CTkFont(size=13, weight="bold"),
            text=f"{source_title}   ->   {target_title}",
            wraplength=460,
        ).grid(row=0, column=0, sticky="ew")

        ctk.CTkLabel(
            body, anchor="w", justify="left", text_color=MUTED,
            font=ctk.CTkFont(size=11), wraplength=460,
            text="A caption for whoever reads the chart. The app never "
                 "evaluates it and never decides which branch is followed.",
        ).grid(row=1, column=0, sticky="ew", pady=(4, 12))

        self.entry = ctk.CTkEntry(
            body, height=38, font=ctk.CTkFont(size=13),
            placeholder_text="e.g. Yes, No, or leave blank for no label",
        )
        self.entry.grid(row=2, column=0, sticky="ew")
        if self._initial:
            self.entry.insert(0, self._initial)

        quick = ctk.CTkFrame(body, fg_color="transparent")
        quick.grid(row=3, column=0, sticky="w", pady=(10, 0))
        ctk.CTkLabel(quick, text="Quick:", text_color=MUTED,
                     font=ctk.CTkFont(size=11)).grid(row=0, column=0, padx=(0, 8))
        for column, text in enumerate(QUICK_LABELS, start=1):
            ctk.CTkButton(
                quick, text=text, width=64, height=28,
                font=ctk.CTkFont(size=12), fg_color="transparent",
                border_width=1, text_color=MUTED,
                command=lambda t=text: self._fill(t),
            ).grid(row=0, column=column, padx=(0, 8))

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=1, column=0, sticky="ew", padx=18, pady=(14, 14))
        footer.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            footer, text="  " + DISCLAIMER + "  ",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#3d2f00", fg_color=WARNING, corner_radius=6,
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))

        # Clearing a label is a deliberate choice, not a cancel - so it gets
        # its own button rather than making the engineer empty the box.
        ctk.CTkButton(
            footer, text="No label", width=90, height=34,
            fg_color="transparent", border_width=1, text_color=MUTED,
            command=self._on_clear,
        ).grid(row=1, column=0, sticky="w")

        ctk.CTkButton(
            footer, text="Cancel", width=90, height=34,
            fg_color="transparent", border_width=1, text_color=MUTED,
            command=self._on_cancel,
        ).grid(row=1, column=1, sticky="e", padx=(0, 8))

        ctk.CTkButton(
            footer, text="Save label", width=110, height=34,
            font=ctk.CTkFont(size=13, weight="bold"), command=self._on_save,
        ).grid(row=1, column=2, sticky="e")

    # ------------------------------------------------------------------
    def _fill(self, text: str) -> None:
        self.entry.delete(0, "end")
        self.entry.insert(0, text)
        self.entry.focus_set()

    def _on_save(self) -> None:
        self.result = self.entry.get().strip()[:MAX_LABEL]
        self._close()

    def _on_clear(self) -> None:
        self.result = ""
        self._close()

    def _on_cancel(self) -> None:
        self.result = None
        self._close()

    def _close(self) -> None:
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()


def ask_edge_label(
    master,
    source_title: str,
    target_title: str,
    initial: str = "",
) -> Optional[str]:
    """Prompt for a connection label.

    Returns None if cancelled, otherwise the label - possibly an empty
    string, meaning "no caption on this arrow".
    """
    dialog = EdgeLabelDialog(master, source_title, target_title, initial)
    master.wait_window(dialog)
    return dialog.result
