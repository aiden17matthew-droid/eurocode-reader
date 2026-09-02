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
from collections import OrderedDict
from typing import Callable, Dict, List, Optional, Tuple

import customtkinter as ctk
from PIL import Image, ImageTk

from backend.flowchart import MAX_LABEL, Flowchart, FlowEdge, FlowNode

from .edge_label_dialog import ask_edge_label
from .equation_render import EquationRenderError, render_image

# --- geometry ---------------------------------------------------------------
NODE_W = 220
NODE_H = 96
DECISION_W = 250
DECISION_H = 136
CORNER_R = 12

# A node showing a formula needs room for it, so it grows rather than
# squeezing the equation into an unreadable strip.
EQUATION_EXTRA_H = 56
EQUATION_PX_HEIGHT = 30       # drawn height at 100% zoom
EQUATION_CACHE = 64

GRID_STEP = 40
SCROLL_PAD = 900          # empty room around the nodes to drag/pan into
EDGE_HIT_TOLERANCE = 8    # px from the line that still counts as a click
ARROW_SHAPE = (14, 17, 5)

# Node positions are stored in world coordinates and multiplied by the zoom
# factor only when drawing, so zooming never touches the saved workflow.
MIN_ZOOM = 0.40
MAX_ZOOM = 2.50
ZOOM_STEP = 1.15          # multiplicative, so each notch feels the same
MIN_FONT_PX = 6           # below this a label is unreadable anyway

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
    width, height = ((DECISION_W, DECISION_H) if node.kind == "decision"
                     else (NODE_W, NODE_H))
    if getattr(node, "equation", None) is not None:
        height += EQUATION_EXTRA_H
    return width, height


def _shorten(text: str, limit: int) -> str:
    """Trim a label to fit on a node without wrapping into a paragraph."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit - 1].rstrip() + "..."


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
      left drag on empty space pan the sheet
      left click on empty      clear the selection
      left click on a ref      open that Eurocode page
      double click on a node   edit it
      double click on an arrow label it
      right click on an arrow  menu: label, clear the label, delete
      middle / right drag      pan the sheet (alternative)
      wheel / shift+wheel      scroll vertically / horizontally
      ctrl + wheel             zoom about the pointer
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
        on_zoom: Optional[Callable[[float], None]] = None,
    ) -> None:
        super().__init__(master, corner_radius=8)

        self.chart = chart
        self.on_edit = on_edit or (lambda _n: None)
        self.on_open_ref = on_open_ref or (lambda _n: None)
        self.on_select = on_select or (lambda _n: None)
        self.on_change = on_change or (lambda: None)
        self.on_status = on_status or (lambda _t: None)
        self.on_zoom = on_zoom or (lambda _z: None)

        self.colors = palette()
        self.connect_mode = False
        self.zoom = 1.0

        self.selected_node: Optional[str] = None
        self.selected_edge: Optional[FlowEdge] = None
        self._connect_source: Optional[str] = None
        self._drag_id: Optional[str] = None
        self._drag_offset = (0.0, 0.0)
        self._drag_moved = False
        self._panning = False
        self._pointer = (0.0, 0.0)
        self._ref_hotspots: Dict[str, Tuple[float, float, float, float]] = {}
        # Typesetting an expression costs tens of milliseconds, which is far
        # too slow to redo on every frame of a drag - so drawn equations are
        # cached by expression, size and colour, and survive a redraw.
        self._equation_photos: "OrderedDict[tuple, ImageTk.PhotoImage]" = \
            OrderedDict()

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

        # Middle drag always pans. Right click opens a menu when it lands on
        # an arrow, and otherwise falls back to panning - left drag is the
        # main pan gesture now, so right click is free to do something useful.
        c.bind("<Button-2>", self._pan_start)
        c.bind("<B2-Motion>", self._pan_move)
        c.bind("<Button-3>", self._on_right_press)
        c.bind("<B3-Motion>", self._pan_move)

        # Wheel bindings stay local to this widget so they cannot fight with
        # the preview window's global wheel handler.
        c.bind("<MouseWheel>", self._on_wheel)
        c.bind("<Shift-MouseWheel>", self._on_shift_wheel)
        c.bind("<Control-MouseWheel>", self._on_ctrl_wheel)
        c.bind("<Button-4>", lambda _e: c.yview_scroll(-3, "units"))
        c.bind("<Button-5>", lambda _e: c.yview_scroll(3, "units"))
        c.bind("<Control-Button-4>", lambda e: self.zoom_at(ZOOM_STEP, e.x, e.y))
        c.bind("<Control-Button-5>", lambda e: self.zoom_at(1 / ZOOM_STEP, e.x, e.y))

        # Keyboard zoom. Tk reports the unshifted key, so both '+' and '=' are
        # bound - otherwise Ctrl+'+' needs the shift key on most layouts.
        for key in ("<Control-plus>", "<Control-equal>", "<Control-KP_Add>"):
            c.bind(key, lambda _e: self.zoom_in())
        for key in ("<Control-minus>", "<Control-KP_Subtract>"):
            c.bind(key, lambda _e: self.zoom_out())
        c.bind("<Control-Key-0>", lambda _e: self.reset_zoom())

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
        if not self.chart.nodes:
            return
        cx = sum(n.x for n in self.chart.nodes) / len(self.chart.nodes)
        cy = sum(n.y for n in self.chart.nodes) / len(self.chart.nodes)
        self.center_on_point(cx, cy)

    def center_on_point(self, world_x: float, world_y: float) -> None:
        """Scroll until a world coordinate sits in the middle of the view."""
        self._update_scrollregion()
        self.canvas.update_idletasks()
        region = self.canvas.cget("scrollregion").split()
        if len(region) != 4:
            return
        rx1, ry1, rx2, ry2 = (float(v) for v in region)
        width = max(1.0, rx2 - rx1)
        height = max(1.0, ry2 - ry1)
        view_w = self.canvas.winfo_width()
        view_h = self.canvas.winfo_height()
        target_x = world_x * self.zoom
        target_y = world_y * self.zoom
        self.canvas.xview_moveto(max(0.0, (target_x - rx1 - view_w / 2) / width))
        self.canvas.yview_moveto(max(0.0, (target_y - ry1 - view_h / 2) / height))

    def bring_into_view(self, node: FlowNode) -> None:
        """Scroll to a node only if it is not already on screen."""
        self.canvas.update_idletasks()
        view_w, view_h = self.canvas.winfo_width(), self.canvas.winfo_height()
        left, top = self.canvas.canvasx(0), self.canvas.canvasy(0)
        x, y = node.x * self.zoom, node.y * self.zoom
        w, h = node_size(node)
        margin_x, margin_y = w * self.zoom / 2, h * self.zoom / 2
        if not (left + margin_x <= x <= left + view_w - margin_x
                and top + margin_y <= y <= top + view_h - margin_y):
            self.center_on_point(node.x, node.y)

    # ------------------------------------------------------------------
    # Zoom
    # ------------------------------------------------------------------
    def zoom_in(self) -> None:
        self._zoom_to_centre(ZOOM_STEP)

    def zoom_out(self) -> None:
        self._zoom_to_centre(1 / ZOOM_STEP)

    def reset_zoom(self) -> None:
        """Back to 100%, keeping whatever is in the middle of the view."""
        self.canvas.update_idletasks()
        cx = self.canvas.canvasx(self.canvas.winfo_width() / 2) / self.zoom
        cy = self.canvas.canvasy(self.canvas.winfo_height() / 2) / self.zoom
        if self._apply_zoom(1.0):
            self.center_on_point(cx, cy)

    def _zoom_to_centre(self, factor: float) -> None:
        self.canvas.update_idletasks()
        self.zoom_at(factor, self.canvas.winfo_width() / 2,
                     self.canvas.winfo_height() / 2)

    def zoom_at(self, factor: float, screen_x: float, screen_y: float) -> None:
        """Zoom about a point on screen, keeping what is under it in place.

        Without the anchor the sheet appears to slide away from the pointer,
        which makes it hard to zoom into the node you are actually looking at.
        """
        old = self.zoom
        # The world point currently under the cursor.
        world_x = self.canvas.canvasx(screen_x) / old
        world_y = self.canvas.canvasy(screen_y) / old

        if not self._apply_zoom(old * factor):
            return

        # Scroll so that same world point lands back under the cursor.
        region = self.canvas.cget("scrollregion").split()
        if len(region) != 4:
            return
        rx1, ry1, rx2, ry2 = (float(v) for v in region)
        width = max(1.0, rx2 - rx1)
        height = max(1.0, ry2 - ry1)
        self.canvas.xview_moveto(
            (world_x * self.zoom - screen_x - rx1) / width
        )
        self.canvas.yview_moveto(
            (world_y * self.zoom - screen_y - ry1) / height
        )

    def _apply_zoom(self, value: float) -> bool:
        """Clamp and set the zoom. Returns False if nothing changed."""
        new = max(MIN_ZOOM, min(MAX_ZOOM, value))
        if abs(new - self.zoom) < 1e-6:
            return False
        self.zoom = new
        self.redraw()
        self.on_zoom(self.zoom)
        return True

    # ------------------------------------------------------------------
    # Drawing
    #
    # The model holds world coordinates. Everything below multiplies by
    # self.zoom on the way to the canvas, and _world() divides on the way
    # back, so the saved workflow is identical at any zoom level.
    # ------------------------------------------------------------------
    def _font(self, spec: Tuple) -> Tuple:
        """A font tuple scaled to the current zoom."""
        family, size = spec[0], spec[1]
        return (family, max(MIN_FONT_PX, int(round(size * self.zoom)))) + tuple(spec[2:])

    def redraw(self) -> None:
        """Clear the sheet and draw it again.

        Nothing in here may force Tk to paint: the canvas has just been
        emptied, so a repaint at this point shows a blank sheet and the
        engineer sees a flash on every frame of a drag. That is why
        _update_scrollregion no longer calls update_idletasks, and why it is
        skipped entirely while a drag is in progress - resizing the sheet
        mid-drag also shifts the view under the pointer.
        """
        c = self.canvas
        c.delete("all")
        self._ref_hotspots.clear()

        if self._drag_id is None and not self._panning:
            self._update_scrollregion()
        self._draw_grid()

        for edge in self.chart.edges:
            self._draw_edge(edge)

        if self.connect_mode and self._connect_source:
            self._draw_pending_edge()

        # Naming the standard on every node is noise on a single-standard
        # chart, but essential once a workflow spans EN 1992 and EN 1997.
        documents = {n.ref.document_title for n in self.chart.nodes if n.ref}
        show_document = len(documents) > 1

        for node in self.chart.nodes:
            self._draw_node(node, show_document=show_document)

        if not self.chart.nodes:
            self._draw_empty_hint()

    def _draw_grid(self) -> None:
        region = self.canvas.cget("scrollregion").split()
        if len(region) != 4:
            return
        x1, y1, x2, y2 = (int(float(v)) for v in region)
        colour = self.colors["grid"]
        # The grid scales with the sheet, but its on-screen spacing is kept
        # sane so zooming out does not turn it into a solid block.
        step = max(24, int(GRID_STEP * 2 * self.zoom))
        start_x = x1 - (x1 % step)
        for x in range(start_x, x2, step):
            self.canvas.create_line(x, y1, x, y2, fill=colour)
        start_y = y1 - (y1 % step)
        for y in range(start_y, y2, step):
            self.canvas.create_line(x1, y, x2, y, fill=colour)

    def _draw_empty_hint(self) -> None:
        # Called from redraw(), so it must not force a paint either.
        x = self.canvas.canvasx(self.canvas.winfo_width() / 2)
        y = self.canvas.canvasy(self.canvas.winfo_height() / 2)
        self.canvas.create_text(
            x, y, width=460, justify="center", fill=self.colors["hint"],
            font=("Segoe UI", 11),
            text="Add a Step or a Decision to begin.\n\n"
                 "Drag nodes to arrange them, drag the background to pan the "
                 "sheet, Ctrl+wheel to zoom, and use Connect to draw arrows. "
                 "Right-click an arrow to label it."
                 "\n\n"
                 "This chart records your workflow - it does not calculate "
                 "anything.",
        )

    def _draw_node(self, node: FlowNode, show_document: bool = False) -> None:
        c = self.canvas
        z = self.zoom
        base_w, base_h = node_size(node)
        w, h = base_w * z, base_h * z
        cx, cy = node.x * z, node.y * z
        x1, y1 = cx - w / 2, cy - h / 2
        x2, y2 = cx + w / 2, cy + h / 2

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
                cx, y1, x2, cy, cx, y2, x1, cy,
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
            text_width = w - 60 * z
        else:
            c.create_polygon(
                _round_rect_points(x1, y1, x2, y2, CORNER_R * z),
                smooth=True, fill=self.colors["node_fill"],
                outline=border, width=width,
            )
            # A coloured spine makes the kind readable at a glance without
            # tinting the whole node.
            c.create_line(x1 + 3 * z, y1 + CORNER_R * z,
                          x1 + 3 * z, y2 - CORNER_R * z,
                          fill=accent, width=max(2, 4 * z))
            text_width = w - 34 * z

        # Kind badge
        badge_y = y1 + (18 if node.kind == "decision" else 14) * z
        c.create_text(
            cx, badge_y, text=KIND_LABELS.get(node.kind, "STEP"),
            fill=accent, font=self._font(META_FONT),
        )

        # Title
        has_ref = node.ref is not None
        has_equation = getattr(node, "equation", None) is not None
        lines_below = (1 if has_ref else 0) + (1 if show_document and has_ref else 0)
        title_y = cy - lines_below * 7 * z
        if has_equation:
            # The node grew to make room, so the title moves up out of it.
            title_y -= (EQUATION_EXTRA_H / 2) * z
        c.create_text(
            cx, title_y, text=node.display_title, width=text_width,
            fill=self.colors["title"], font=self._font(TITLE_FONT),
            justify="center",
        )

        # The formula, drawn beneath the title. It is a picture of the
        # expression - the canvas never reads it for meaning.
        if has_equation:
            photo = self._equation_photo(
                node, text_width, max(10.0, EQUATION_PX_HEIGHT * z)
            )
            if photo is not None:
                c.create_image(
                    cx, title_y + 16 * z + photo.height() / 2, image=photo,
                )
            else:
                # It will not typeset - name it rather than drawing nothing.
                c.create_text(
                    cx, title_y + 26 * z,
                    text=f"[{node.equation.display_name}]",
                    fill=self.colors["meta"], font=self._font(NOTE_FONT),
                    width=text_width, justify="center",
                )

        # Notes marker - the notes themselves live in the editor, so a busy
        # node never turns into a wall of text on the canvas.
        if node.notes:
            c.create_text(
                x2 - 12 * z, y1 + 14 * z, text="[notes]", anchor="e",
                fill=self.colors["meta"], font=self._font(NOTE_FONT),
            )

        # Eurocode pointer - clicking this opens the page.
        if has_ref:
            ref_y = y2 - (26 if node.kind == "decision" else 18) * z

            # Which standard this step points at. Only drawn once a workflow
            # spans more than one document - on a single-standard chart the
            # same title on every node is noise.
            if show_document:
                c.create_text(
                    cx, ref_y - 13 * z,
                    text=_shorten(node.ref.document_title, 34),
                    fill=self.colors["meta"], font=self._font(NOTE_FONT),
                    width=text_width, justify="center",
                )

            item = c.create_text(
                cx, ref_y, text=node.ref.label, fill=self.colors["ref"],
                font=self._font(REF_FONT), width=text_width, justify="center",
            )
            bbox = c.bbox(item)
            if bbox:
                # Stored in world coordinates so hit-testing stays zoom-free.
                self._ref_hotspots[node.id] = (
                    (bbox[0] - 4) / z, (bbox[1] - 3) / z,
                    (bbox[2] + 4) / z, (bbox[3] + 3) / z,
                )

    def _draw_edge(self, edge: FlowEdge) -> None:
        source = self.chart.node_by_id(edge.source_id)
        target = self.chart.node_by_id(edge.target_id)
        if source is None or target is None:
            return

        z = self.zoom
        sx, sy = self._boundary(source, target.x, target.y)
        tx, ty = self._boundary(target, source.x, source.y)
        sx, sy, tx, ty = sx * z, sy * z, tx * z, ty * z

        selected = self.selected_edge is edge
        self.canvas.create_line(
            sx, sy, tx, ty,
            fill=self.colors["selected"] if selected else self.colors["edge"],
            width=max(1, (3 if selected else 2) * z),
            arrow="last", arrowshape=self._arrow_shape(), capstyle="round",
        )

        if edge.label:
            mx, my = (sx + tx) / 2, (sy + ty) / 2
            item = self.canvas.create_text(
                mx, my, text=edge.label, fill=self.colors["edge_label"],
                font=self._font(LABEL_FONT),
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
        z = self.zoom
        px, py = self._pointer
        sx, sy = self._boundary(source, px, py)
        self.canvas.create_line(
            sx * z, sy * z, px * z, py * z, fill=self.colors["source"],
            width=max(1, 2 * z), dash=(6, 4), arrow="last",
            arrowshape=self._arrow_shape(),
        )

    def _equation_photo(self, node: FlowNode, max_w: float, max_h: float):
        """The node's formula, drawn to fit inside the space available."""
        equation = node.equation
        if equation is None or max_w < 8 or max_h < 6:
            return None

        colour = self.colors["title"]
        key = (equation.latex, int(max_w), int(max_h), colour)
        cached = self._equation_photos.get(key)
        if cached is not None:
            self._equation_photos.move_to_end(key)
            return cached

        try:
            image = render_image(equation.latex, px_height=int(max_h),
                                 color=colour)
        except EquationRenderError:
            # A formula that will not typeset must not stop the node drawing.
            return None

        if image.width > max_w:
            ratio = max_w / image.width
            image = image.resize(
                (max(1, int(image.width * ratio)),
                 max(1, int(image.height * ratio))),
                Image.LANCZOS,
            )

        photo = ImageTk.PhotoImage(image)
        self._equation_photos[key] = photo
        while len(self._equation_photos) > EQUATION_CACHE:
            self._equation_photos.popitem(last=False)
        return photo

    def _arrow_shape(self):
        """Arrowheads scale with the sheet, but never shrink into a dot."""
        z = max(0.7, self.zoom)
        return tuple(max(4, v * z) for v in ARROW_SHAPE)

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
        # No update_idletasks here - see redraw(). winfo_width is accurate
        # once the window has been laid out, and <Configure> brings us back
        # if it changes.
        view_w = max(self.canvas.winfo_width(), 400)
        view_h = max(self.canvas.winfo_height(), 300)

        # The scroll region lives in canvas coordinates, so it is the world
        # bounding box multiplied by the zoom.
        z = self.zoom
        if self.chart.nodes:
            xs, ys = [], []
            for node in self.chart.nodes:
                w, h = node_size(node)
                xs += [(node.x - w / 2) * z, (node.x + w / 2) * z]
                ys += [(node.y - h / 2) * z, (node.y + h / 2) * z]
            pad = SCROLL_PAD * z
            x1, x2 = min(xs) - pad, max(xs) + pad
            y1, y2 = min(ys) - pad, max(ys) + pad
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
        """Widget coordinates -> world coordinates, undoing pan and zoom."""
        return (self.canvas.canvasx(event.x) / self.zoom,
                self.canvas.canvasy(event.y) / self.zoom)

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
            # The tolerance is in screen pixels, so convert it to world units
            # - an arrow must stay equally easy to click at any zoom.
            if _point_to_segment(x, y, sx, sy, tx, ty) <= EDGE_HIT_TOLERANCE / self.zoom:
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
            start_x = self.canvas.canvasx(self.canvas.winfo_width() / 2) / self.zoom
            start_y = self.canvas.canvasy(self.canvas.winfo_height() / 2) / self.zoom

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
            self._handle_connect_click(x, y, event)
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
                f"{target.display_title}. Right-click or double-click it to "
                f"add a label, or press Delete to remove it."
            )
            return

        # Empty background: the click has already cleared the selection, and
        # holding and moving now drags the sheet. This is the gesture people
        # expect from every other canvas tool - reaching for a middle button
        # to pan is not something a trackpad user can do at all.
        self._start_pan(event)

    def _on_drag(self, event) -> None:
        if self._panning:
            self.canvas.scan_dragto(event.x, event.y, gain=1)
            return
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
        was_dragging = self._drag_id is not None and self._drag_moved
        if was_dragging:
            self.chart.touch()
            self.on_change()

        self._drag_id = None
        self._drag_moved = False
        self._panning = False

        # Deferred from redraw(), which skips this while a drag is running:
        # growing the sheet mid-drag shifts the view under the pointer.
        if was_dragging:
            self._update_scrollregion()
        self.canvas.configure(cursor="tcross" if self.connect_mode else "")

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
            return

        edge = self._edge_at(x, y)
        if edge is not None:
            # The press handler will have started a pan on the way here.
            self._panning = False
            self.canvas.configure(cursor="")
            self.label_edge(edge)

    def _on_motion(self, event) -> None:
        x, y = self._world(event)
        self._pointer = (x, y)

        if self.connect_mode:
            if self._connect_source:
                self.redraw()
            return

        over_ref = self._ref_at(x, y) is not None
        self.canvas.configure(cursor="hand2" if over_ref else "")

    def _handle_connect_click(self, x: float, y: float, event=None) -> None:
        node = self._node_at(x, y)
        if node is None:
            self._cancel_connect()
            # Still pan: the sheet has to be navigable while wiring up a
            # chart that is bigger than the window.
            if event is not None:
                self._start_pan(event)
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
        """Offered when a branch leaves a decision, where readers need to tell
        the routes apart. Every other arrow can be labelled later, or not at
        all - most sequential steps do not need a caption."""
        answer = ask_edge_label(
            self, source.display_title, target.display_title, ""
        )
        return answer or ""

    def _cancel_connect(self) -> None:
        if self._connect_source is not None:
            self._connect_source = None
            self.redraw()
            self.on_status("Connection cancelled.")

    # ------------------------------------------------------------------
    # Pan and scroll
    # ------------------------------------------------------------------
    def _on_right_press(self, event) -> None:
        """Menu on an arrow, pan anywhere else."""
        self.canvas.focus_set()
        if not self.connect_mode:
            x, y = self._world(event)
            edge = self._edge_at(x, y)
            if edge is not None:
                self.selected_node = None
                self.selected_edge = edge
                self.redraw()
                self.on_select(None)
                self._show_edge_menu(event, edge)
                return "break"
        self._start_pan(event)

    def _show_edge_menu(self, event, edge: FlowEdge) -> None:
        """Context menu for one connection.

        A raw tk.Menu does not follow the CustomTkinter theme, so it takes
        its colours from the same palette as the canvas.
        """
        colours = self.colors
        menu = tk.Menu(
            self.canvas, tearoff=0,
            background=colours["node_fill"], foreground=colours["title"],
            activebackground=colours["selected"], activeforeground="#ffffff",
            borderwidth=1, relief="solid",
        )
        menu.add_command(
            label="Edit label..." if edge.label else "Add label...",
            command=lambda: self.label_edge(edge),
        )
        if edge.label:
            menu.add_command(
                label="Remove label",
                command=lambda: self.set_edge_label(edge, ""),
            )
        menu.add_separator()
        menu.add_command(
            label="Delete connection",
            command=lambda: self._delete_edge(edge),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    # ------------------------------------------------------------------
    # Labelling
    # ------------------------------------------------------------------
    def label_edge(self, edge: FlowEdge) -> None:
        """Ask for this connection's caption and apply the answer."""
        source = self.chart.node_by_id(edge.source_id)
        target = self.chart.node_by_id(edge.target_id)
        if source is None or target is None:
            return

        answer = ask_edge_label(
            self, source.display_title, target.display_title, edge.label
        )
        if answer is None:              # cancelled - leave the label alone
            return
        self.set_edge_label(edge, answer)

    def set_edge_label(self, edge: FlowEdge, label: str) -> None:
        """Apply a caption. An empty string means the arrow carries none."""
        cleaned = (label or "").strip()[:MAX_LABEL]
        if cleaned == edge.label:
            return
        edge.label = cleaned
        self.chart.touch()
        self.on_change()
        self.redraw()

        source = self.chart.node_by_id(edge.source_id)
        target = self.chart.node_by_id(edge.target_id)
        route = (f"{source.display_title} -> {target.display_title}"
                 if source and target else "connection")
        self.on_status(
            f"Labelled '{route}' as \"{cleaned}\"." if cleaned
            else f"Removed the label from '{route}'."
        )

    def _delete_edge(self, edge: FlowEdge) -> None:
        self.selected_edge = edge
        self.selected_node = None
        self.delete_selection()

    def _start_pan(self, event) -> None:
        """Begin dragging the sheet from wherever the pointer is."""
        self._drag_id = None
        self._panning = True
        self.canvas.scan_mark(event.x, event.y)
        self.canvas.configure(cursor="fleur")

    def _pan_start(self, event) -> None:
        self.canvas.focus_set()
        self._start_pan(event)

    def _pan_move(self, event) -> None:
        # Without this guard a right-drag that began on a context menu would
        # scroll from a stale scan mark and make the sheet jump.
        if not self._panning:
            return
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    def _on_wheel(self, event) -> None:
        self.canvas.yview_scroll(int(-event.delta / 60), "units")

    def _on_shift_wheel(self, event) -> None:
        self.canvas.xview_scroll(int(-event.delta / 60), "units")

    def _on_ctrl_wheel(self, event) -> None:
        """Ctrl + wheel zooms about the pointer rather than scrolling."""
        factor = ZOOM_STEP if event.delta > 0 else 1 / ZOOM_STEP
        self.zoom_at(factor, event.x, event.y)
        return "break"      # do not also scroll


def _point_to_segment(px, py, x1, y1, x2, y2) -> float:
    """Shortest distance from a point to a line segment."""
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    nx, ny = x1 + t * dx, y1 + t * dy
    return ((px - nx) ** 2 + (py - ny) ** 2) ** 0.5
