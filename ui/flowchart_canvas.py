"""The drawing surface for the Flowchart Builder.

A plain ``tk.Canvas``, because CustomTkinter has no canvas of its own and the
arrows between nodes need real line drawing, hit-testing and panning.

A raw Canvas does not follow the CustomTkinter theme, so every colour comes
from :func:`palette`, which is re-read from ``ctk.get_appearance_mode()`` on
each full redraw.

Nothing here interprets a node. Titles, notes and branch labels are drawn as
the engineer typed them; the canvas never evaluates a decision or computes a
value.
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Dict, List, Optional, Tuple

import customtkinter as ctk

from backend.flowchart import Flowchart, FlowEdge, FlowNode

# --- geometry ---------------------------------------------------------------
NODE_W = 220
NODE_H = 96
DECISION_W = 250
DECISION_H = 136
CORNER_R = 12

GRID_STEP = 40
SCROLL_PAD = 900          # empty room around the nodes to drag/pan into
EDGE_HIT_TOLERANCE = 8    # px from the line that still counts as a click
ARROW_SHAPE = (14, 17, 5)

TITLE_FONT = ("Segoe UI", 11, "bold")
META_FONT = ("Segoe UI", 8)
REF_FONT = ("Segoe UI", 9, "underline")
NOTE_FONT = ("Segoe UI", 8)
LABEL_FONT = ("Segoe UI", 9, "bold")

KIND_LABELS = {
    "start": "START",
    "process": "STEP",
    "decision": "DECISION",
    "end": "END",
}


def palette() -> Dict[str, str]:
    """Colours for the current CustomTkinter appearance mode."""
    dark = ctk.get_appearance_mode() == "Dark"
    if dark:
        return {
            "bg": "#1d1f22",
            "grid": "#26292d",
            "node_fill": "#2b2f34",
            "node_border": "#434a52",
            "title": "#e9ecef",
            "meta": "#7d8792",
            "notes": "#a5aeb8",
            "ref": "#5aa9e6",
            "edge": "#7f8b98",
            "edge_label": "#c3ccd5",
            "selected": "#3b8ed0",
            "source": "#e0a800",
            "hint": "#6f7a85",
            "start": "#4c9a6a",
            "process": "#3b8ed0",
            "decision": "#e0a800",
            "end": "#c0576b",
        }
    return {
        "bg": "#f4f6f8",
        "grid": "#e6eaee",
        "node_fill": "#ffffff",
        "node_border": "#c6cfd8",
        "title": "#1b2733",
        "meta": "#8894a0",
        "notes": "#5d6975",
        "ref": "#1f6aa5",
        "edge": "#77838f",
        "edge_label": "#44505c",
        "selected": "#3b8ed0",
        "source": "#b98600",
        "hint": "#93a0ac",
        "start": "#3f8a5d",
        "process": "#3b8ed0",
        "decision": "#c79100",
        "end": "#b04a5e",
    }


def node_size(node: FlowNode) -> Tuple[int, int]:
    if node.kind == "decision":
        return DECISION_W, DECISION_H
    return NODE_W, NODE_H


def _round_rect_points(x1, y1, x2, y2, r):
    """Corner points that render as a rounded rectangle with smooth=True."""
    return [
        x1 + r, y1, x1 + r, y1, x2 - r, y1, x2 - r, y1, x2, y1,
        x2, y1 + r, x2, y1 + r, x2, y2 - r, x2, y2 - r, x2, y2,
        x2 - r, y2, x2 - r, y2, x1 + r, y2, x1 + r, y2, x1, y2,
        x1, y2 - r, x1, y2 - r, x1, y1 + r, x1, y1 + r, x1, y1,
    ]


class FlowchartCanvas(ctk.CTkFrame):
    """Draws a :class:`Flowchart` and lets the engineer arrange it.

    Mouse:
      left drag on a node      move it
      left click on empty      clear the selection
      left click on a ref      open that Eurocode page
      double click on a node   edit it
      middle / right drag      pan the sheet
      wheel / shift+wheel      scroll
    In Connect mode a left click picks the source node, the next picks the
    target, and the arrow is drawn between them.
    """

    def __init__(
        self,
        master,
        chart: Flowchart,
        on_edit: Optional[Callable[[FlowNode], None]] = None,
        on_open_ref: Optional[Callable[[FlowNode], None]] = None,
        on_select: Optional[Callable[[Optional[FlowNode]], None]] = None,
        on_change: Optional[Callable[[], None]] = None,
        on_status: Optional[Callable[[str], None]] = None,
    ) -> None:
        super().__init__(master, corner_radius=8)

        self.chart = chart
        self.on_edit = on_edit or (lambda _n: None)
        self.on_open_ref = on_open_ref or (lambda _n: None)
        self.on_select = on_select or (lambda _n: None)
        self.on_change = on_change or (lambda: None)
        self.on_status = on_status or (lambda _t: None)

        self.colors = palette()
        self.connect_mode = False

        self.selected_node: Optional[str] = None
        self.selected_edge: Optional[FlowEdge] = None
        self._connect_source: Optional[str] = None
        self._drag_id: Optional[str] = None
        self._drag_offset = (0.0, 0.0)
        self._drag_moved = False
        self._pointer = (0.0, 0.0)
        self._ref_hotspots: Dict[str, Tuple[float, float, float, float]] = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            self, background=self.colors["bg"], highlightthickness=0,
            takefocus=True,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")

        self.v_scroll = ctk.CTkScrollbar(
            self, orientation="vertical", command=self.canvas.yview
        )
        self.v_scroll.grid(row=0, column=1, sticky="ns")
        self.h_scroll = ctk.CTkScrollbar(
            self, orientation="horizontal", command=self.canvas.xview
        )
        self.h_scroll.grid(row=1, column=0, sticky="ew")
        self.canvas.configure(
            yscrollcommand=self.v_scroll.set, xscrollcommand=self.h_scroll.set
        )

        self._bind_events()
        self.after(50, self.redraw)

    # ------------------------------------------------------------------
    # Bindings
    # ------------------------------------------------------------------
    def _bind_events(self) -> None:
        c = self.canvas
        c.bind("<Button-1>", self._on_press)
        c.bind("<B1-Motion>", self._on_drag)
        c.bind("<ButtonRelease-1>", self._on_release)
        c.bind("<Double-Button-1>", self._on_double_click)
        c.bind("<Motion>", self._on_motion)

        # Pan with either middle or right drag - trackpads rarely have a
        # middle button, and a right drag is a familiar pan gesture.
        for button in ("2", "3"):
            c.bind(f"<Button-{button}>", self._pan_start)
            c.bind(f"<B{button}-Motion>", self._pan_move)

        # Wheel bindings stay local to this widget so they cannot fight with
        # the preview window's global wheel handler.
        c.bind("<MouseWheel>", self._on_wheel)
        c.bind("<Shift-MouseWheel>", self._on_shift_wheel)
        c.bind("<Button-4>", lambda _e: c.yview_scroll(-3, "units"))
        c.bind("<Button-5>", lambda _e: c.yview_scroll(3, "units"))

        c.bind("<Delete>", lambda _e: self.delete_selection())
        c.bind("<BackSpace>", lambda _e: self.delete_selection())
        c.bind("<Escape>", lambda _e: self._cancel_connect())
        c.bind("<Configure>", lambda _e: self._update_scrollregion())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_chart(self, chart: Flowchart) -> None:
        self.chart = chart
        self.selected_node = None
        self.selected_edge = None
        self._connect_source = None
        self._drag_id = None
        self.on_select(None)
        self.redraw()
        self.center_on_content()

    def set_connect_mode(self, enabled: bool) -> None:
        self.connect_mode = bool(enabled)
        self._connect_source = None
        self.canvas.configure(cursor="tcross" if enabled else "")
        if enabled:
            self.on_status(
                "Connect mode: click the node the arrow starts from, "
                "then the node it points to. Esc to cancel."
            )
        self.redraw()

    def refresh_theme(self) -> None:
        """Re-read the appearance mode and repaint."""
        self.colors = palette()
        self.canvas.configure(background=self.colors["bg"])
        self.redraw()

    def _set_appearance_mode(self, mode_string: str) -> None:
        """CustomTkinter calls this on every widget when the theme changes.

        A raw tk.Canvas is invisible to the theme system, so this is where the
        hand-picked palette gets swapped - including when the OS switches
        between light and dark while the app is running.
        """
        super()._set_appearance_mode(mode_string)
        try:
            self.refresh_theme()
        except tk.TclError:      # widget already torn down
            pass

    def add_node(self, kind: str, title: str = "") -> FlowNode:
        """Drop a new node into the middle of the current view."""
        x, y = self._free_spot(kind)
        node = FlowNode(title=title, kind=kind, x=x, y=y)
        self.chart.add_node(node)
        self.selected_node = node.id
        self.selected_edge = None
        self.on_change()
        self.redraw()
        self.on_select(node)
        return node

    def delete_selection(self) -> None:
        if self.selected_node:
            node = self.chart.node_by_id(self.selected_node)
            if node is not None:
                dropped = len(self.chart.edges_for(node.id))
                self.chart.remove_node(node.id)
                self.selected_node = None
                self.on_change()
                self.redraw()
                self.on_select(None)
                extra = f" and {dropped} connection(s)" if dropped else ""
                self.on_status(f"Deleted '{node.display_title}'{extra}.")
            return

        if self.selected_edge is not None:
            self.chart.remove_edge(self.selected_edge)
            self.selected_edge = None
            self.on_change()
            self.redraw()
            self.on_status("Deleted the connection.")

    def selected(self) -> Optional[FlowNode]:
        if self.selected_node is None:
            return None
        return self.chart.node_by_id(self.selected_node)

    def center_on_content(self) -> None:
        """Scroll so the existing nodes are in view."""
        self._update_scrollregion()
        if not self.chart.nodes:
            return
        self.canvas.update_idletasks()
        region = self.canvas.cget("scrollregion").split()
        if len(region) != 4:
            return
        rx1, ry1, rx2, ry2 = (float(v) for v in region)
        width = max(1.0, rx2 - rx1)
        height = max(1.0, ry2 - ry1)
        cx = sum(n.x for n in self.chart.nodes) / len(self.chart.nodes)
        cy = sum(n.y for n in self.chart.nodes) / len(self.chart.nodes)
        view_w = self.canvas.winfo_width()
        view_h = self.canvas.winfo_height()
        self.canvas.xview_moveto(max(0.0, (cx - rx1 - view_w / 2) / width))
        self.canvas.yview_moveto(max(0.0, (cy - ry1 - view_h / 2) / height))

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def redraw(self) -> None:
        c = self.canvas
        c.delete("all")
        self._ref_hotspots.clear()

        self._update_scrollregion()
        self._draw_grid()

        for edge in self.chart.edges:
            self._draw_edge(edge)

        if self.connect_mode and self._connect_source:
            self._draw_pending_edge()

        for node in self.chart.nodes:
            self._draw_node(node)

        if not self.chart.nodes:
            self._draw_empty_hint()

    def _draw_grid(self) -> None:
        region = self.canvas.cget("scrollregion").split()
        if len(region) != 4:
            return
        x1, y1, x2, y2 = (int(float(v)) for v in region)
        colour = self.colors["grid"]
        start_x = x1 - (x1 % GRID_STEP)
        for x in range(start_x, x2, GRID_STEP * 2):
            self.canvas.create_line(x, y1, x, y2, fill=colour)
        start_y = y1 - (y1 % GRID_STEP)
        for y in range(start_y, y2, GRID_STEP * 2):
            self.canvas.create_line(x1, y, x2, y, fill=colour)

    def _draw_empty_hint(self) -> None:
        self.canvas.update_idletasks()
        x = self.canvas.canvasx(self.canvas.winfo_width() / 2)
        y = self.canvas.canvasy(self.canvas.winfo_height() / 2)
        self.canvas.create_text(
            x, y, width=460, justify="center", fill=self.colors["hint"],
            font=("Segoe UI", 11),
            text="Add a Step or a Decision to begin.\n\n"
                 "Drag nodes to arrange them, drag the sheet with the right "
                 "mouse button to pan, and use Connect to draw arrows.\n\n"
                 "This chart records your workflow - it does not calculate "
                 "anything.",
        )

    def _draw_node(self, node: FlowNode) -> None:
        c = self.canvas
        w, h = node_size(node)
        x1, y1 = node.x - w / 2, node.y - h / 2
        x2, y2 = node.x + w / 2, node.y + h / 2

        accent = self.colors.get(node.kind, self.colors["process"])
        is_selected = node.id == self.selected_node
        is_source = node.id == self._connect_source

        if is_source:
            border, width = self.colors["source"], 3
        elif is_selected:
            border, width = self.colors["selected"], 3
        else:
            border, width = self.colors["node_border"], 1

        if node.kind == "decision":
            c.create_polygon(
                node.x, y1, x2, node.y, node.x, y2, x1, node.y,
                fill=self.colors["node_fill"], outline=border, width=width,
            )
            text_width = w * 0.52
        elif node.kind in ("start", "end"):
            radius = h / 2
            c.create_polygon(
                _round_rect_points(x1, y1, x2, y2, radius),
                smooth=True, fill=self.colors["node_fill"],
                outline=border, width=width,
            )
            text_width = w - 60
        else:
            c.create_polygon(
                _round_rect_points(x1, y1, x2, y2, CORNER_R),
                smooth=True, fill=self.colors["node_fill"],
                outline=border, width=width,
            )
            # A coloured spine makes the kind readable at a glance without
            # tinting the whole node.
            c.create_line(x1 + 3, y1 + CORNER_R, x1 + 3, y2 - CORNER_R,
                          fill=accent, width=4)
            text_width = w - 34

        # Kind badge
        badge_y = y1 + (18 if node.kind == "decision" else 14)
        c.create_text(
            node.x, badge_y, text=KIND_LABELS.get(node.kind, "STEP"),
            fill=accent, font=META_FONT,
        )

        # Title
        has_ref = node.ref is not None
        title_y = node.y - (6 if has_ref else 0)
        c.create_text(
            node.x, title_y, text=node.display_title, width=text_width,
            fill=self.colors["title"], font=TITLE_FONT, justify="center",
        )

        # Notes marker - the notes themselves live in the editor, so a busy
        # node never turns into a wall of text on the canvas.
        if node.notes:
            c.create_text(
                x2 - 12, y1 + 14, text="[notes]", anchor="e",
                fill=self.colors["meta"], font=NOTE_FONT,
            )

        # Eurocode pointer - clicking this opens the page.
        if has_ref:
            ref_y = y2 - (26 if node.kind == "decision" else 18)
            item = c.create_text(
                node.x, ref_y, text=node.ref.label, fill=self.colors["ref"],
                font=REF_FONT, width=text_width, justify="center",
            )
            bbox = c.bbox(item)
            if bbox:
                self._ref_hotspots[node.id] = (
                    bbox[0] - 4, bbox[1] - 3, bbox[2] + 4, bbox[3] + 3,
                )

    def _draw_edge(self, edge: FlowEdge) -> None:
        source = self.chart.node_by_id(edge.source_id)
        target = self.chart.node_by_id(edge.target_id)
        if source is None or target is None:
            return

        sx, sy = self._boundary(source, target.x, target.y)
        tx, ty = self._boundary(target, source.x, source.y)

        selected = self.selected_edge is edge
        self.canvas.create_line(
            sx, sy, tx, ty,
            fill=self.colors["selected"] if selected else self.colors["edge"],
            width=3 if selected else 2,
            arrow="last", arrowshape=ARROW_SHAPE, capstyle="round",
        )

        if edge.label:
            mx, my = (sx + tx) / 2, (sy + ty) / 2
            item = self.canvas.create_text(
                mx, my, text=edge.label, fill=self.colors["edge_label"],
                font=LABEL_FONT,
            )
            bbox = self.canvas.bbox(item)
            if bbox:
                # Punch a hole in the line so the caption stays readable.
                patch = self.canvas.create_rectangle(
                    bbox[0] - 5, bbox[1] - 2, bbox[2] + 5, bbox[3] + 2,
                    fill=self.colors["bg"], outline="",
                )
                self.canvas.tag_lower(patch, item)

    def _draw_pending_edge(self) -> None:
        source = self.chart.node_by_id(self._connect_source)
        if source is None:
            return
        px, py = self._pointer
        sx, sy = self._boundary(source, px, py)
        self.canvas.create_line(
            sx, sy, px, py, fill=self.colors["source"], width=2,
            dash=(6, 4), arrow="last", arrowshape=ARROW_SHAPE,
        )

    def _boundary(self, node: FlowNode, toward_x: float, toward_y: float):
        """Where the line from the node's centre leaves its outline."""
        w, h = node_size(node)
        dx, dy = toward_x - node.x, toward_y - node.y
        if abs(dx) < 1e-6 and abs(dy) < 1e-6:
            return node.x, node.y

        half_w, half_h = w / 2, h / 2
        if node.kind == "decision":
            # |x|/a + |y|/b = 1 for a diamond.
            scale = 1.0 / (abs(dx) / half_w + abs(dy) / half_h)
        else:
            candidates = []
            if abs(dx) > 1e-6:
                candidates.append(half_w / abs(dx))
            if abs(dy) > 1e-6:
                candidates.append(half_h / abs(dy))
            scale = min(candidates)
        return node.x + dx * scale, node.y + dy * scale

    def _update_scrollregion(self) -> None:
        self.canvas.update_idletasks()
        view_w = max(self.canvas.winfo_width(), 400)
        view_h = max(self.canvas.winfo_height(), 300)

        if self.chart.nodes:
            xs, ys = [], []
            for node in self.chart.nodes:
                w, h = node_size(node)
                xs += [node.x - w / 2, node.x + w / 2]
                ys += [node.y - h / 2, node.y + h / 2]
            x1, x2 = min(xs) - SCROLL_PAD, max(xs) + SCROLL_PAD
            y1, y2 = min(ys) - SCROLL_PAD, max(ys) + SCROLL_PAD
        else:
            x1, y1, x2, y2 = 0.0, 0.0, float(view_w), float(view_h)

        # Never let the sheet be smaller than the window, or Tk clamps the
        # view and panning feels stuck.
        if x2 - x1 < view_w:
            x2 = x1 + view_w
        if y2 - y1 < view_h:
            y2 = y1 + view_h
        self.canvas.configure(scrollregion=(x1, y1, x2, y2))

    # ------------------------------------------------------------------
    # Hit testing
    # ------------------------------------------------------------------
    def _world(self, event) -> Tuple[float, float]:
        return self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

    def _node_at(self, x: float, y: float) -> Optional[FlowNode]:
        # Reverse order: the most recently added node sits on top.
        for node in reversed(self.chart.nodes):
            w, h = node_size(node)
            dx, dy = abs(x - node.x), abs(y - node.y)
            if node.kind == "decision":
                if dx / (w / 2) + dy / (h / 2) <= 1.0:
                    return node
            elif dx <= w / 2 and dy <= h / 2:
                return node
        return None

    def _ref_at(self, x: float, y: float) -> Optional[FlowNode]:
        for node_id, (x1, y1, x2, y2) in self._ref_hotspots.items():
            if x1 <= x <= x2 and y1 <= y <= y2:
                return self.chart.node_by_id(node_id)
        return None

    def _edge_at(self, x: float, y: float) -> Optional[FlowEdge]:
        for edge in self.chart.edges:
            source = self.chart.node_by_id(edge.source_id)
            target = self.chart.node_by_id(edge.target_id)
            if source is None or target is None:
                continue
            sx, sy = self._boundary(source, target.x, target.y)
            tx, ty = self._boundary(target, source.x, source.y)
            if _point_to_segment(x, y, sx, sy, tx, ty) <= EDGE_HIT_TOLERANCE:
                return edge
        return None

    def _overlaps(self, x: float, y: float, w: float, h: float,
                  margin: float = 20.0) -> bool:
        """True if a node of this size at (x, y) would collide with another."""
        for node in self.chart.nodes:
            nw, nh = node_size(node)
            if (abs(x - node.x) < (w + nw) / 2 + margin
                    and abs(y - node.y) < (h + nh) / 2 + margin):
                return True
        return False

    def _free_spot(self, kind: str) -> Tuple[float, float]:
        """Somewhere clear to drop a new node.

        A flowchart is built top to bottom, so a new node lands under the
        selected one where the next step belongs. Otherwise it goes to the
        middle of the view. Either way it is nudged by whole node widths until
        it is not sitting on top of anything - testing the centre point alone
        is not enough, since two boxes can overlap almost completely while
        their centres are apart.
        """
        self.canvas.update_idletasks()
        w, h = node_size(FlowNode(title="", kind=kind))

        anchor = self.selected()
        if anchor is not None:
            start_x = anchor.x
            start_y = anchor.y + (node_size(anchor)[1] + h) / 2 + 70
        else:
            start_x = self.canvas.canvasx(self.canvas.winfo_width() / 2)
            start_y = self.canvas.canvasy(self.canvas.winfo_height() / 2)

        for column in range(8):
            for row in range(8):
                x = start_x + column * (w + 60)
                y = start_y + row * (h + 50)
                if not self._overlaps(x, y, w, h):
                    return x, y
        return start_x, start_y      # crowded sheet - the engineer can drag it

    # ------------------------------------------------------------------
    # Mouse
    # ------------------------------------------------------------------
    def _on_press(self, event) -> None:
        self.canvas.focus_set()
        x, y = self._world(event)

        if self.connect_mode:
            self._handle_connect_click(x, y)
            return

        # The reference is a hyperlink sitting on top of the node, so it must
        # be tested before the node itself.
        ref_node = self._ref_at(x, y)
        if ref_node is not None:
            self.selected_node = ref_node.id
            self.selected_edge = None
            self.redraw()
            self.on_select(ref_node)
            self.on_open_ref(ref_node)
            return

        node = self._node_at(x, y)
        if node is not None:
            self.selected_node = node.id
            self.selected_edge = None
            self._drag_id = node.id
            self._drag_offset = (x - node.x, y - node.y)
            self._drag_moved = False
            self.canvas.configure(cursor="fleur")
            self.redraw()
            self.on_select(node)
            return

        edge = self._edge_at(x, y)
        self.selected_node = None
        self.selected_edge = edge
        self.redraw()
        self.on_select(None)
        if edge is not None:
            source = self.chart.node_by_id(edge.source_id)
            target = self.chart.node_by_id(edge.target_id)
            self.on_status(
                f"Connection selected: {source.display_title} -> "
                f"{target.display_title}. Press Delete to remove it."
            )

    def _on_drag(self, event) -> None:
        if self._drag_id is None:
            return
        node = self.chart.node_by_id(self._drag_id)
        if node is None:
            self._drag_id = None
            return
        x, y = self._world(event)
        node.x = x - self._drag_offset[0]
        node.y = y - self._drag_offset[1]
        self._drag_moved = True
        self.redraw()

    def _on_release(self, _event) -> None:
        if self._drag_id is not None and self._drag_moved:
            self.chart.touch()
            self.on_change()
            self._update_scrollregion()
        self._drag_id = None
        self._drag_moved = False
        if not self.connect_mode:
            self.canvas.configure(cursor="")

    def _on_double_click(self, event) -> None:
        if self.connect_mode:
            return
        x, y = self._world(event)
        node = self._node_at(x, y)
        if node is not None:
            # A double click also fires the press handler, which may have
            # started a drag - cancel it so the node does not jump.
            self._drag_id = None
            self.on_edit(node)

    def _on_motion(self, event) -> None:
        x, y = self._world(event)
        self._pointer = (x, y)

        if self.connect_mode:
            if self._connect_source:
                self.redraw()
            return

        over_ref = self._ref_at(x, y) is not None
        self.canvas.configure(cursor="hand2" if over_ref else "")

    def _handle_connect_click(self, x: float, y: float) -> None:
        node = self._node_at(x, y)
        if node is None:
            self._cancel_connect()
            return

        if self._connect_source is None:
            self._connect_source = node.id
            self.redraw()
            self.on_status(
                f"From '{node.display_title}' - now click the node this "
                f"arrow points to."
            )
            return

        if node.id == self._connect_source:
            self.on_status("A node cannot connect to itself. Pick another node.")
            return

        source = self.chart.node_by_id(self._connect_source)
        label = ""
        if source is not None and source.kind == "decision":
            # Decision branches need a caption so a reader can tell them
            # apart. It is a caption only - the app never tests it.
            label = self._ask_branch_label(source, node)

        edge = self.chart.add_edge(self._connect_source, node.id, label)
        self._connect_source = None
        self.on_change()
        self.redraw()
        if edge is not None and source is not None:
            caption = f" ({edge.label})" if edge.label else ""
            self.on_status(
                f"Connected '{source.display_title}' -> "
                f"'{node.display_title}'{caption}. "
                f"Click another node to keep connecting, or leave Connect mode."
            )

    def _ask_branch_label(self, source: FlowNode, target: FlowNode) -> str:
        dialog = ctk.CTkInputDialog(
            title="Branch label",
            text=f"Label for the branch from '{source.display_title}' to "
                 f"'{target.display_title}'.\n\n"
                 f"Typically Yes or No. This is a caption for the reader - "
                 f"the app never evaluates it.\n\nLeave blank for no label.",
        )
        value = dialog.get_input()
        return (value or "").strip()

    def _cancel_connect(self) -> None:
        if self._connect_source is not None:
            self._connect_source = None
            self.redraw()
            self.on_status("Connection cancelled.")

    # ------------------------------------------------------------------
    # Pan and scroll
    # ------------------------------------------------------------------
    def _pan_start(self, event) -> None:
        self.canvas.focus_set()
        self.canvas.scan_mark(event.x, event.y)
        self.canvas.configure(cursor="fleur")

    def _pan_move(self, event) -> None:
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    def _on_wheel(self, event) -> None:
        self.canvas.yview_scroll(int(-event.delta / 60), "units")

    def _on_shift_wheel(self, event) -> None:
        self.canvas.xview_scroll(int(-event.delta / 60), "units")


def _point_to_segment(px, py, x1, y1, x2, y2) -> float:
    """Shortest distance from a point to a line segment."""
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    nx, ny = x1 + t * dx, y1 + t * dy
    return ((px - nx) ** 2 + (py - ny) ** 2) ** 0.5
