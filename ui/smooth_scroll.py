"""Wheel scrolling that keeps up with the mouse.

CustomTkinter's scrollable frame scrolls a fixed ``delta / 6`` units, and on
Windows it sets the canvas increment to one pixel - so a wheel notch moves the
view 20 pixels. A browser moves about 100, which is why the stock behaviour
feels like dragging the content rather than flicking it.

This binds a faster handler directly on the scrollable frame and everything
inside it. Because a widget-level binding runs before the "all" tag, returning
"break" stops CustomTkinter's slower global handler from scrolling as well -
otherwise both would fire and the view would jump.
"""

from __future__ import annotations

import tkinter as tk
from typing import Optional

import customtkinter as ctk

# Roughly what a browser moves per notch.
PIXELS_PER_NOTCH = 110
WHEEL_NOTCH = 120          # what Windows reports for one detent

# Linux sends button presses instead of a delta.
LINUX_UP, LINUX_DOWN = "<Button-4>", "<Button-5>"


class SmoothScroller:
    """Fast wheel scrolling for one CTkScrollableFrame.

    Call :meth:`refresh` after adding widgets to the frame: Tk delivers a
    wheel event to the widget under the pointer and does not pass it up to
    parents, so every new child needs the binding too.
    """

    def __init__(
        self,
        frame: ctk.CTkScrollableFrame,
        pixels_per_notch: int = PIXELS_PER_NOTCH,
    ) -> None:
        self.frame = frame
        self.pixels_per_notch = max(10, int(pixels_per_notch))
        self.canvas = frame._parent_canvas
        self.refresh()

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """(Re-)bind the wheel on the frame and everything inside it."""
        self._attach(self.canvas)
        self._attach(self.frame)

    def _attach(self, widget) -> None:
        # Bind through tkinter's own method rather than the widget's.
        # CustomTkinter overrides bind() to forward to its internal canvas
        # with add=True forced, so calling it on every refresh would stack a
        # fresh handler each time and the view would scroll further and
        # further per notch. tkinter's bind replaces instead, which is what
        # re-binding should do. The internal canvases and labels are reached
        # anyway, as children, in the loop below.
        try:
            tk.Misc.bind(widget, "<MouseWheel>", self._on_wheel)
            tk.Misc.bind(widget, "<Shift-MouseWheel>", self._on_shift_wheel)
            tk.Misc.bind(widget, LINUX_UP, lambda _e: self._scroll(-1))
            tk.Misc.bind(widget, LINUX_DOWN, lambda _e: self._scroll(1))
        except tk.TclError:
            return
        for child in widget.winfo_children():
            # A nested scrollable area looks after its own wheel events.
            if isinstance(child, ctk.CTkScrollableFrame):
                continue
            self._attach(child)

    def is_bound(self, widget) -> bool:
        """Whether this widget carries our wheel handler.

        Reads the binding table directly: asking a CustomTkinter widget with
        bind(sequence) would install a null callback rather than report one.
        """
        try:
            return bool(tk.Misc.bind(widget, "<MouseWheel>"))
        except tk.TclError:
            return False

    # ------------------------------------------------------------------
    def _units(self) -> int:
        """How many scroll units make up one notch on this canvas."""
        try:
            increment = int(self.canvas.cget("yscrollincrement") or 0)
        except (tk.TclError, ValueError):
            increment = 0
        if increment <= 0:
            # With no increment set, a unit is a tenth of the viewport.
            return 1
        return max(1, round(self.pixels_per_notch / increment))

    def _notches(self, delta: int) -> int:
        """Wheel delta -> whole notches, never rounding a flick down to zero."""
        notches = int(-delta / WHEEL_NOTCH)
        if notches == 0:
            notches = -1 if delta > 0 else 1
        return notches

    def _scroll(self, notches: int) -> str:
        if self.canvas.yview() != (0.0, 1.0):
            self.canvas.yview_scroll(notches * self._units(), "units")
        return "break"

    def _on_wheel(self, event) -> str:
        return self._scroll(self._notches(event.delta))

    def _on_shift_wheel(self, event) -> str:
        if self.canvas.xview() != (0.0, 1.0):
            self.canvas.xview_scroll(
                self._notches(event.delta) * self._units(), "units"
            )
        return "break"


def smooth_scroll(
    frame: ctk.CTkScrollableFrame,
    pixels_per_notch: int = PIXELS_PER_NOTCH,
) -> SmoothScroller:
    """Give a scrollable frame browser-speed wheel scrolling."""
    return SmoothScroller(frame, pixels_per_notch=pixels_per_notch)
