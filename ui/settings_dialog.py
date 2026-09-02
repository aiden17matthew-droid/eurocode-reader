"""Appearance and interface size.

Changes preview live, so the engineer can see what 150% actually looks like
before committing to it, and Cancel puts back exactly what was there before.

Presentation only: nothing on this screen changes what a search returns or
what a clause says.
"""

from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

from backend.branding import APP_NAME
from backend.settings import (
    APPEARANCE_MODES,
    Settings,
    choice_labels,
    scale_from_label,
    scale_label,
)

MUTED = "#8a8a8a"
ACCENT = "#3b8ed0"


def apply_settings(settings: Settings) -> None:
    """Make CustomTkinter match these preferences."""
    ctk.set_appearance_mode(settings.appearance)
    # CustomTkinter scales widgets and their fonts together, so this one
    # control is both "UI scaling" and "font size".
    ctk.set_widget_scaling(settings.ui_scale)
    ctk.set_window_scaling(settings.ui_scale)


class SettingsDialog(ctk.CTkToplevel):
    """Theme and interface size, previewed live. ``saved`` says if applied."""

    def __init__(
        self,
        master,
        settings: Settings,
        on_change: Optional[Callable[[Settings], None]] = None,
    ) -> None:
        super().__init__(master)

        self.settings = settings
        self.saved = False
        self.on_change = on_change or (lambda _s: None)

        # What to put back if they change their mind.
        self._original = Settings(appearance=settings.appearance,
                                  ui_scale=settings.ui_scale,
                                  path=settings.path)

        self.title(f"{APP_NAME} settings")
        self.geometry("520x430")
        self.minsize(460, 400)
        self.resizable(False, False)

        self._build_layout()

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.bind("<Escape>", lambda _e: self._on_cancel())

        self.transient(master)
        self.after(80, self._focus)

    def _focus(self) -> None:
        try:
            self.grab_set()
            self.lift()
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=0, column=0, sticky="nsew", padx=22, pady=(20, 0))
        body.grid_columnconfigure(0, weight=1)
        row = 0

        # --- appearance ---------------------------------------------------
        ctk.CTkLabel(body, text="Appearance", anchor="w",
                     font=ctk.CTkFont(size=13, weight="bold")
                     ).grid(row=row, column=0, sticky="ew")
        row += 1
        ctk.CTkLabel(
            body, anchor="w", justify="left", text_color=MUTED,
            font=ctk.CTkFont(size=11), wraplength=440,
            text="System follows whatever Windows is set to, and keeps "
                 "following it if you change that later.",
        ).grid(row=row, column=0, sticky="ew", pady=(2, 8))
        row += 1

        self.appearance_var = ctk.StringVar(value=self.settings.appearance)
        appearance_row = ctk.CTkFrame(body, fg_color="transparent")
        appearance_row.grid(row=row, column=0, sticky="ew", pady=(0, 18))
        for column, mode in enumerate(APPEARANCE_MODES):
            appearance_row.grid_columnconfigure(column, weight=1)
            ctk.CTkRadioButton(
                appearance_row, text=mode, value=mode,
                variable=self.appearance_var, font=ctk.CTkFont(size=12),
                command=self._preview,
            ).grid(row=0, column=column, sticky="w", padx=(0, 12))
        row += 1

        # --- interface size -----------------------------------------------
        ctk.CTkLabel(body, text="Interface size", anchor="w",
                     font=ctk.CTkFont(size=13, weight="bold")
                     ).grid(row=row, column=0, sticky="ew")
        row += 1
        ctk.CTkLabel(
            body, anchor="w", justify="left", text_color=MUTED,
            font=ctk.CTkFont(size=11), wraplength=440,
            text="Scales the whole interface, text included. The flowchart "
                 "sheet keeps its own zoom control (Ctrl + wheel).",
        ).grid(row=row, column=0, sticky="ew", pady=(2, 8))
        row += 1

        self.scale_menu = ctk.CTkOptionMenu(
            body, values=choice_labels(), height=34, width=140,
            command=lambda _v: self._preview(),
        )
        self.scale_menu.set(scale_label(self.settings.ui_scale))
        self.scale_menu.grid(row=row, column=0, sticky="w", pady=(0, 6))
        row += 1

        self.sample_label = ctk.CTkLabel(
            body, anchor="w", justify="left",
            text="Sample: v_Rd,c = C_Rd,c k (100 rho_l f_ck)^(1/3)",
            font=ctk.CTkFont(size=12),
        )
        self.sample_label.grid(row=row, column=0, sticky="ew", pady=(4, 0))
        row += 1

        self.note_label = ctk.CTkLabel(
            body, anchor="w", justify="left", text_color=ACCENT,
            font=ctk.CTkFont(size=11), wraplength=440, text="",
        )
        self.note_label.grid(row=row, column=0, sticky="ew", pady=(10, 0))
        row += 1

        # --- footer ---------------------------------------------------------
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=1, column=0, sticky="ew", padx=22, pady=(12, 18))
        footer.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            footer, text="Reset to defaults", width=140, height=34,
            fg_color="transparent", border_width=1, text_color=MUTED,
            command=self._on_reset,
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            footer, text="Cancel", width=90, height=34,
            fg_color="transparent", border_width=1, text_color=MUTED,
            command=self._on_cancel,
        ).grid(row=0, column=1, sticky="e", padx=(0, 8))

        ctk.CTkButton(
            footer, text="Save", width=110, height=34,
            font=ctk.CTkFont(size=13, weight="bold"), command=self._on_save,
        ).grid(row=0, column=2, sticky="e")

    # ------------------------------------------------------------------
    def _current(self) -> Settings:
        return Settings(
            appearance=self.appearance_var.get(),
            ui_scale=scale_from_label(self.scale_menu.get()),
            path=self.settings.path,
        )

    def _preview(self) -> None:
        """Apply straight away - guessing what 150% looks like is no fun."""
        chosen = self._current()
        apply_settings(chosen)
        self.note_label.configure(
            text=f"Previewing {chosen.appearance.lower()} theme at "
                 f"{chosen.scale_percent}. Save to keep it."
        )

    def _on_reset(self) -> None:
        defaults = Settings(path=self.settings.path)
        self.appearance_var.set(defaults.appearance)
        self.scale_menu.set(scale_label(defaults.ui_scale))
        self._preview()

    def _on_save(self) -> None:
        chosen = self._current()
        self.settings.appearance = chosen.appearance
        self.settings.ui_scale = chosen.ui_scale
        apply_settings(self.settings)
        try:
            self.settings.save()
        except OSError:
            # Not being able to remember the choice is no reason to refuse
            # to apply it for this session.
            pass
        self.saved = True
        self.on_change(self.settings)
        self._close()

    def _on_cancel(self) -> None:
        # Put back exactly what was showing before the dialog opened.
        apply_settings(self._original)
        self.saved = False
        self._close()

    def _close(self) -> None:
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()


def edit_settings(
    master,
    settings: Settings,
    on_change: Optional[Callable[[Settings], None]] = None,
) -> bool:
    """Open Settings modally. Returns True if the engineer saved."""
    dialog = SettingsDialog(master, settings=settings, on_change=on_change)
    master.wait_window(dialog)
    return dialog.saved
