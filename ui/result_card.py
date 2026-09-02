"""A single search result: a pointer to a page/clause, plus a text snippet."""

from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

from backend.indexer import SearchHit

ACCENT = "#3b8ed0"
MUTED = "#8a8a8a"
WARNING = "#e0a800"

# On a maximised window a card can be ~1850 px wide. Text that long is hard to
# scan: the eye loses its place on the return sweep. Cap the measure.
MAX_TEXT_WIDTH = 980
MIN_TEXT_WIDTH = 240
TEXT_PADDING = 60

HINT_TEXT = "Click to open this page"
ADD_TEXT = "+ Add to Flowchart"


class ResultCard(ctk.CTkFrame):
    """Clickable card showing where an answer lives in the engineer's PDF.

    Displays the location pointer and a verbatim snippet only - never an
    interpretation, calculation or recommendation.
    """

    def __init__(
        self,
        master,
        hit: SearchHit,
        rank: int,
        on_open: Callable[[SearchHit], None],
        weak: bool = False,
        on_add: Optional[Callable[[SearchHit], None]] = None,
    ) -> None:
        super().__init__(master, corner_radius=8, fg_color=("#f0f0f0", "#2b2b2b"))

        self.hit = hit
        self.on_open = on_open
        self.on_add = on_add
        self.weak = weak
        # A pointer crossing the card fires Enter on every child widget it
        # passes over. Re-applying the highlight each time repaints the whole
        # frame - about ten milliseconds a go - which is what made hovering
        # the results feel like dragging them. Track the state and only
        # repaint when it actually changes.
        self._hovered = False
        self._default_color = ("#f0f0f0", "#2b2b2b")
        self._hover_color = ("#e4ecf5", "#35404a")

        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 0))
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            header, text=f"{rank}.", width=22, anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"), text_color=MUTED,
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header, text=hit.location_label, anchor="w",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=WARNING if weak else ACCENT,
        ).grid(row=0, column=1, sticky="w")

        # Relevance is a retrieval score, not an engineering confidence.
        ctk.CTkLabel(
            header, text=f"match {hit.score:.0%}", anchor="e",
            font=ctk.CTkFont(size=11, weight="bold" if weak else "normal"),
            text_color=WARNING if weak else MUTED,
        ).grid(row=0, column=2, sticky="e")

        ctk.CTkLabel(
            self, text=hit.document_title, anchor="w",
            font=ctk.CTkFont(size=11), text_color=MUTED,
        ).grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 4))

        # A weak match is shown only because the engineer asked to see them.
        # Label it plainly so it is never mistaken for a confident pointer.
        if weak:
            ctk.CTkLabel(
                self, anchor="w", justify="left",
                text="Weak match - below the relevance threshold. "
                     "This page may have nothing to do with your query.",
                font=ctk.CTkFont(size=11), text_color=WARNING,
            ).grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 6))

        self.snippet_label = ctk.CTkLabel(
            self, text=hit.snippet, anchor="w", justify="left",
            wraplength=MAX_TEXT_WIDTH, font=ctk.CTkFont(size=12),
        )
        self.snippet_label.grid(row=3, column=0, sticky="ew", padx=14)

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=4, column=0, sticky="ew", padx=14, pady=(4, 10))
        footer.grid_columnconfigure(0, weight=1)

        # The hint only appears on hover. The label stays gridded with its text
        # blanked, so the card keeps its height and rows do not jump.
        self.hint_label = ctk.CTkLabel(
            footer, text="", anchor="w",
            font=ctk.CTkFont(size=10), text_color=MUTED,
        )
        self.hint_label.grid(row=0, column=0, sticky="w")

        # Sends this result to the Flowchart tab. It must NOT open the PDF, so
        # it is excluded from the card-wide click binding below.
        self.add_button: Optional[ctk.CTkButton] = None
        if on_add is not None:
            self.add_button = ctk.CTkButton(
                footer, text=ADD_TEXT, width=140, height=26,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color="transparent", border_width=1, text_color=ACCENT,
                command=self._on_add_clicked,
            )
            self.add_button.grid(row=0, column=1, sticky="e")

        self._bind_recursive(self)

    def _bind_recursive(self, widget) -> None:
        """Make the whole card clickable, not just its background.

        The Add button is skipped, along with everything inside it: the card
        binds <Button-1> on every descendant, so without this the button's
        click would also reach the card and open the PDF preview.
        """
        if self.add_button is not None and widget is self.add_button:
            return
        widget.bind("<Button-1>", self._on_click)
        widget.bind("<Enter>", self._on_enter)
        widget.bind("<Leave>", self._on_leave)
        for child in widget.winfo_children():
            self._bind_recursive(child)

    def set_wraplength(self, width: int) -> None:
        """Follow the card width, but never exceed a comfortable measure."""
        usable = min(width - TEXT_PADDING, MAX_TEXT_WIDTH)
        self.snippet_label.configure(wraplength=max(MIN_TEXT_WIDTH, usable))

    def _covers(self, x_root: int, y_root: int) -> bool:
        """True if a screen point falls inside this card.

        Plain arithmetic on the card's own geometry. The obvious alternative,
        winfo_containing(), asks the window manager which widget is under the
        pointer - a round trip that is far too slow to run on every Leave
        event, and scrolling a list of cards generates a great many of them.
        """
        try:
            left, top = self.winfo_rootx(), self.winfo_rooty()
            return (left <= x_root < left + self.winfo_width()
                    and top <= y_root < top + self.winfo_height())
        except Exception:
            return False

    def _on_click(self, _event=None) -> None:
        self.on_open(self.hit)

    def _on_add_clicked(self) -> None:
        """Send this result to the flowchart. Never opens the preview."""
        if self.on_add is not None:
            self.on_add(self.hit)

    def _on_enter(self, _event=None) -> None:
        if self._hovered:
            return
        self._hovered = True
        self.configure(fg_color=self._hover_color, cursor="hand2")
        self.hint_label.configure(text=HINT_TEXT)

    def _on_leave(self, event=None) -> None:
        # Moving between a card's own children fires Leave then Enter. Ignore
        # the Leave if the pointer is still somewhere inside this card,
        # otherwise the highlight and hint flicker.
        if event is not None and self._covers(event.x_root, event.y_root):
            return
        if not self._hovered:
            return

        self._hovered = False
        self.configure(fg_color=self._default_color, cursor="")
        self.hint_label.configure(text="")
