"""What this app is, and - just as importantly - what it is not.

Every claim on this screen is one the app has to keep: it runs offline, it
points at clauses rather than interpreting them, it never solves an equation,
and it is nobody's official publication.
"""

from __future__ import annotations

import customtkinter as ctk

from backend.branding import (
    APP_NAME,
    APP_TAGLINE,
    DISCLAIMER,
    NOT_AFFILIATED,
    NOT_CALCULATED,
    OFFLINE_NOTE,
)

MUTED = "#8a8a8a"
ACCENT = "#3b8ed0"
WARNING = "#e0a800"


class AboutDialog(ctk.CTkToplevel):
    """A short, honest description of the tool."""

    def __init__(self, master) -> None:
        super().__init__(master)

        self.title(f"About {APP_NAME}")
        self.geometry("560x520")
        self.minsize(480, 460)
        self.resizable(False, False)

        self._build_layout()

        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Escape>", lambda _e: self._close())
        self.bind("<Return>", lambda _e: self._close())

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
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=0, column=0, sticky="nsew", padx=24, pady=(22, 0))
        body.grid_columnconfigure(0, weight=1)
        row = 0

        ctk.CTkLabel(
            body, text=APP_NAME, anchor="w",
            font=ctk.CTkFont(size=24, weight="bold"), text_color=ACCENT,
        ).grid(row=row, column=0, sticky="ew")
        row += 1

        ctk.CTkLabel(
            body, text=APP_TAGLINE, anchor="w", justify="left",
            font=ctk.CTkFont(size=12), text_color=MUTED, wraplength=490,
        ).grid(row=row, column=0, sticky="ew", pady=(2, 16))
        row += 1

        ctk.CTkLabel(
            body, anchor="w", justify="left", wraplength=490,
            font=ctk.CTkFont(size=12),
            text="Search, read and cross-reference the Eurocode PDFs you "
                 "already own, and build design workflows that point at them.",
        ).grid(row=row, column=0, sticky="ew", pady=(0, 14))
        row += 1

        for text in (OFFLINE_NOTE, NOT_CALCULATED):
            ctk.CTkLabel(
                body, text=text, anchor="w", justify="left", wraplength=490,
                font=ctk.CTkFont(size=12), text_color=MUTED,
            ).grid(row=row, column=0, sticky="ew", pady=(0, 10))
            row += 1

        # The two notices that matter most, given prominence rather than
        # buried in a paragraph.
        ctk.CTkLabel(
            body, text="  " + DISCLAIMER + "  ", anchor="w", justify="left",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#3d2f00", fg_color=WARNING, corner_radius=6,
            wraplength=470,
        ).grid(row=row, column=0, sticky="ew", pady=(6, 8))
        row += 1

        ctk.CTkLabel(
            body, text=NOT_AFFILIATED, anchor="w", justify="left",
            wraplength=490, font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=1, column=0, sticky="ew", padx=24, pady=(10, 18))
        footer.grid_columnconfigure(0, weight=1)

        self.close_button = ctk.CTkButton(
            footer, text="Close", width=110, height=36,
            font=ctk.CTkFont(size=13, weight="bold"), command=self._close,
        )
        self.close_button.grid(row=0, column=1, sticky="e")

    def _close(self) -> None:
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()


def show_about(master) -> None:
    """Open the About box modally."""
    dialog = AboutDialog(master)
    master.wait_window(dialog)
