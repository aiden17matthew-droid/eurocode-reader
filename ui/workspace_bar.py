"""The workspace strip under the header: which project state is open, and the
explicit controls to save or load one.

Presentation only. The shell owns the actual save/load logic, because a
workspace spans both tabs and the index.

The wording here matters: every button is an action the engineer takes
deliberately. Nothing on this bar happens on a timer.
"""

from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

from .services import reflow_row

MUTED = "#8a8a8a"
ACCENT = "#3b8ed0"
DIRTY_COLOR = "#e0a800"

MAX_NAME_CHARS = 42


class WorkspaceBar(ctk.CTkFrame):
    """Shows the open workspace and offers Load / Save / Save As."""

    def __init__(
        self,
        master,
        on_load: Callable[[], None],
        on_save: Callable[[], None],
        on_save_as: Callable[[], None],
    ) -> None:
        super().__init__(master, fg_color="transparent")

        self._wrapped = False

        self.grid_columnconfigure(0, weight=1)

        self.left = ctk.CTkFrame(self, fg_color="transparent")
        self.left.grid(row=0, column=0, sticky="w")

        self.right = ctk.CTkFrame(self, fg_color="transparent")
        self.right.grid(row=0, column=1, sticky="e")

        ctk.CTkLabel(
            self.left, text="Workspace:", text_color=MUTED,
            font=ctk.CTkFont(size=12),
        ).grid(row=0, column=0, padx=(0, 8))

        self.name_label = ctk.CTkLabel(
            self.left, text="(none)", anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=ACCENT,
        )
        self.name_label.grid(row=0, column=1, sticky="w")

        self.detail_label = ctk.CTkLabel(
            self.left, text="", anchor="w",
            font=ctk.CTkFont(size=11), text_color=MUTED,
        )
        self.detail_label.grid(row=0, column=2, sticky="w", padx=(10, 0))

        ctk.CTkButton(
            self.right, text="Load Workspace...", width=140, height=30,
            fg_color="transparent", border_width=1, text_color=MUTED,
            font=ctk.CTkFont(size=12), command=on_load,
        ).grid(row=0, column=0)

        self.save_button = ctk.CTkButton(
            self.right, text="Save Workspace", width=130, height=30,
            font=ctk.CTkFont(size=12, weight="bold"), command=on_save,
        )
        self.save_button.grid(row=0, column=1, padx=(8, 0))

        ctk.CTkButton(
            self.right, text="Save As...", width=100, height=30,
            fg_color="transparent", border_width=1, text_color=MUTED,
            font=ctk.CTkFont(size=12), command=on_save_as,
        ).grid(row=0, column=2, padx=(8, 0))

        self.bind("<Configure>", lambda _e: self.reflow())

    # ------------------------------------------------------------------
    def set_workspace(
        self,
        name: Optional[str],
        detail: str = "",
        unsaved: bool = False,
    ) -> None:
        """Show which workspace is open and whether it has unsaved changes."""
        if not name:
            self.name_label.configure(text="(none)", text_color=MUTED)
            self.detail_label.configure(text=detail)
            return

        shown = name if len(name) <= MAX_NAME_CHARS else name[:MAX_NAME_CHARS - 1] + "..."
        # The marker is the engineer's cue that a rollback point is stale -
        # nothing is written until they press Save.
        self.name_label.configure(
            text=shown + (" *" if unsaved else ""),
            text_color=DIRTY_COLOR if unsaved else ACCENT,
        )
        self.detail_label.configure(text=detail)

    def reflow(self) -> None:
        self._wrapped = reflow_row(self, self.left, self.right, self._wrapped)
