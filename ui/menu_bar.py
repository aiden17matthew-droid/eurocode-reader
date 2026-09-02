"""A menu bar built from CustomTkinter widgets.

Windows draws a native ``tk.Menu`` with its own colours and ignores anything
the application asks for, so a dark-themed app ends up wearing a white menu
bar. This is the same thing built out of CTk widgets instead, so it follows
the appearance mode like everything else.

It behaves the way a menu bar should: click a title to open it, click again
to close, slide sideways to move between open menus, Escape or a click
anywhere else to dismiss.
"""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import customtkinter as ctk

SEPARATOR = "---"

BAR_HEIGHT = 30
ITEM_HEIGHT = 28
ITEM_PAD_X = 14
MIN_MENU_WIDTH = 170

MUTED = "#8a8a8a"


def _palette() -> Dict[str, object]:
    """Colours that follow the appearance mode."""
    dark = ctk.get_appearance_mode() == "Dark"
    return {
        "bar": ("#e2e5e9", "#1c1e21"),
        "surface": "#24272b" if dark else "#fbfbfc",
        "border": "#3a4046" if dark else "#c8ced5",
        "text": "#e9ecef" if dark else "#1b2733",
        "hover": "#3b8ed0",
        "hover_text": "#ffffff",
        "separator": "#3a4046" if dark else "#dfe4e9",
    }


@dataclass
class MenuItem:
    """One line in a dropdown. A separator carries no label or command."""

    label: str = ""
    command: Optional[Callable[[], None]] = None
    accelerator: str = ""
    separator: bool = False

    @classmethod
    def divider(cls) -> "MenuItem":
        return cls(separator=True)


class _MenuRow(ctk.CTkFrame):
    """A clickable row: label on the left, shortcut on the right."""

    def __init__(self, master, item: MenuItem, colors, on_pick):
        super().__init__(master, fg_color="transparent", corner_radius=4,
                         height=ITEM_HEIGHT)
        self.item = item
        self.colors = colors
        self.on_pick = on_pick

        self.grid_columnconfigure(0, weight=1)

        self.label = ctk.CTkLabel(
            self, text=item.label, anchor="w",
            font=ctk.CTkFont(size=12), text_color=colors["text"],
        )
        self.label.grid(row=0, column=0, sticky="ew",
                        padx=(ITEM_PAD_X, 10), pady=3)

        self.accel = ctk.CTkLabel(
            self, text=item.accelerator, anchor="e",
            font=ctk.CTkFont(size=11), text_color=MUTED,
        )
        self.accel.grid(row=0, column=1, sticky="e", padx=(0, ITEM_PAD_X))

        for widget in (self, self.label, self.accel):
            widget.bind("<Button-1>", self._on_click)
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)

    def _on_click(self, _event=None) -> None:
        self.on_pick(self.item)

    def _on_enter(self, _event=None) -> None:
        self.configure(fg_color=self.colors["hover"], cursor="hand2")
        self.label.configure(text_color=self.colors["hover_text"])
        self.accel.configure(text_color=self.colors["hover_text"])

    def _on_leave(self, _event=None) -> None:
        self.configure(fg_color="transparent", cursor="")
        self.label.configure(text_color=self.colors["text"])
        self.accel.configure(text_color=MUTED)


class MenuBar(ctk.CTkFrame):
    """The strip of menu titles, and the dropdown they open."""

    def __init__(
        self,
        master,
        menus: Sequence[Tuple[str, Sequence[MenuItem]]],
    ) -> None:
        colors = _palette()
        super().__init__(master, height=BAR_HEIGHT, corner_radius=0,
                         fg_color=colors["bar"])

        self.menus: Dict[str, List[MenuItem]] = {
            name: list(items) for name, items in menus
        }
        self.order: List[str] = [name for name, _items in menus]
        self.buttons: Dict[str, ctk.CTkButton] = {}

        self._popup: Optional[tk.Toplevel] = None
        self._open_name: Optional[str] = None
        self._colors = colors

        self.grid_columnconfigure(len(self.order), weight=1)

        for column, name in enumerate(self.order):
            button = ctk.CTkButton(
                self, text=name, width=10, height=BAR_HEIGHT - 6,
                corner_radius=4, fg_color="transparent",
                hover_color=("#cfd5db", "#33373c"),
                text_color=colors["text"], font=ctk.CTkFont(size=12),
                command=lambda n=name: self.toggle_menu(n),
            )
            button.grid(row=0, column=column, padx=(4 if column else 6, 0),
                        pady=3)
            # Sliding sideways with a menu open switches to that menu, the
            # way every other menu bar behaves.
            button.bind("<Enter>", lambda _e, n=name: self._on_hover(n))
            self.buttons[name] = button

        root = self.winfo_toplevel()
        root.bind("<Escape>", lambda _e: self.close_menu(), add="+")
        # A click anywhere outside the dropdown dismisses it. Clicks inside
        # go to the popup's own window and never reach this binding.
        root.bind("<Button-1>", self._on_root_click, add="+")

    # ------------------------------------------------------------------
    # Introspection - also what the tests drive
    # ------------------------------------------------------------------
    def menu_names(self) -> List[str]:
        return list(self.order)

    def item_labels(self, menu: str) -> List[str]:
        return [SEPARATOR if item.separator else item.label
                for item in self.menus.get(menu, ())]

    def accelerator(self, menu: str, label: str) -> str:
        for item in self.menus.get(menu, ()):
            if not item.separator and item.label == label:
                return item.accelerator
        return ""

    def invoke(self, menu: str, label: str) -> bool:
        """Run a menu item by name. Returns False if there is no such item."""
        for item in self.menus.get(menu, ()):
            if not item.separator and item.label == label:
                self.close_menu()
                if item.command is not None:
                    item.command()
                return True
        return False

    @property
    def open_menu_name(self) -> Optional[str]:
        return self._open_name

    # ------------------------------------------------------------------
    # Opening and closing
    # ------------------------------------------------------------------
    def toggle_menu(self, name: str) -> None:
        if self._open_name == name:
            self.close_menu()
        else:
            self.open_menu(name)

    def _on_hover(self, name: str) -> None:
        if self._open_name is not None and self._open_name != name:
            self.open_menu(name)

    def open_menu(self, name: str) -> None:
        self.close_menu()
        if name not in self.menus:
            return

        button = self.buttons[name]
        colors = _palette()
        self._colors = colors

        popup = tk.Toplevel(self)
        # A bare Toplevel rather than a CTkToplevel: this needs no title bar,
        # and overrideredirect on a CTk window fights its own decoration code.
        popup.overrideredirect(True)
        popup.configure(background=colors["border"])
        popup.attributes("-topmost", True)

        surface = ctk.CTkFrame(popup, corner_radius=6,
                               fg_color=colors["surface"],
                               border_width=1, border_color=colors["border"])
        surface.pack(padx=1, pady=1, fill="both", expand=True)
        surface.grid_columnconfigure(0, weight=1)

        for row, item in enumerate(self.menus[name]):
            if item.separator:
                line = ctk.CTkFrame(surface, height=1, corner_radius=0,
                                    fg_color=colors["separator"])
                line.grid(row=row, column=0, sticky="ew", padx=8, pady=4)
            else:
                _MenuRow(surface, item, colors, self._pick).grid(
                    row=row, column=0, sticky="ew", padx=4,
                    pady=(2 if row == 0 else 0, 0),
                )

        popup.update_idletasks()
        width = max(MIN_MENU_WIDTH, surface.winfo_reqwidth() + 2)
        height = surface.winfo_reqheight() + 8
        x = button.winfo_rootx()
        y = button.winfo_rooty() + button.winfo_height() + 2
        popup.geometry(f"{width}x{height}+{x}+{y}")

        self._popup = popup
        self._open_name = name
        button.configure(fg_color=("#cfd5db", "#33373c"))

    def close_menu(self) -> None:
        if self._popup is not None:
            try:
                self._popup.destroy()
            except tk.TclError:
                pass
            self._popup = None
        if self._open_name is not None:
            button = self.buttons.get(self._open_name)
            if button is not None:
                try:
                    button.configure(fg_color="transparent")
                except tk.TclError:
                    pass
            self._open_name = None

    def _pick(self, item: MenuItem) -> None:
        self.close_menu()
        if item.command is not None:
            item.command()

    def _on_root_click(self, event) -> None:
        if self._open_name is None:
            return
        # Clicking the title that is already open is handled by the button
        # itself, which would otherwise reopen what this just closed.
        button = self.buttons.get(self._open_name)
        if button is not None and _within(button, event.x_root, event.y_root):
            return
        self.close_menu()

    def refresh_theme(self) -> None:
        """Repaint the bar after an appearance change."""
        colors = _palette()
        self._colors = colors
        self.configure(fg_color=colors["bar"])
        for button in self.buttons.values():
            button.configure(text_color=colors["text"])
        self.close_menu()

    def _set_appearance_mode(self, mode_string: str) -> None:
        super()._set_appearance_mode(mode_string)
        try:
            self.refresh_theme()
        except tk.TclError:      # already torn down
            pass


def _within(widget, x_root: int, y_root: int) -> bool:
    try:
        left, top = widget.winfo_rootx(), widget.winfo_rooty()
        return (left <= x_root < left + widget.winfo_width()
                and top <= y_root < top + widget.winfo_height())
    except tk.TclError:
        return False
