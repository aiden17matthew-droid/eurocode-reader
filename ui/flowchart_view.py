"""The Flowchart Builder tab.

The engineer lays out their own design sequence, tags each step with a page or
clause from a Eurocode PDF they own, and saves the workflow as JSON so it can
be reused and shared around the office.

Strictly organisational. Nothing on this tab solves an equation, evaluates a
decision, or produces a value - it records the route and points at the source.
"""

from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Callable, Optional

import customtkinter as ctk

from backend.flowchart import (
    DISCLAIMER,
    Flowchart,
    FlowchartError,
    FlowNode,
    resolve_document_path,
)
from backend.indexer import Indexer

from .flowchart_canvas import FlowchartCanvas
from .node_editor import edit_node
from .services import AsyncRunner, PreviewManager

MUTED = "#8a8a8a"
ACCENT = "#3b8ed0"

FILE_TYPES = [("Flowchart JSON", "*.json"), ("All files", "*.*")]


class FlowchartView(ctk.CTkFrame):
    """Build, arrange, save and reload Eurocode design workflows."""

    def __init__(
        self,
        master,
        indexer: Indexer,
        runner: AsyncRunner,
        preview: PreviewManager,
        set_status: Callable[[str], None],
    ) -> None:
        super().__init__(master, fg_color="transparent")

        self.indexer = indexer
        self.runner = runner
        self.preview = preview
        self.set_status = set_status

        self.chart = Flowchart()
        self.file_path: Optional[Path] = None
        self.dirty = False

        self._build_layout()
        self._update_title()
        self._update_selection_controls(None)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # --- file row ---------------------------------------------------
        file_row = ctk.CTkFrame(self, fg_color="transparent")
        file_row.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 0))
        file_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(file_row, text="Workflow:", text_color=MUTED).grid(
            row=0, column=0, padx=(0, 8)
        )

        self.name_entry = ctk.CTkEntry(
            file_row, height=32, font=ctk.CTkFont(size=13),
            placeholder_text="e.g. Pile design check sequence",
        )
        self.name_entry.grid(row=0, column=1, sticky="ew")
        self.name_entry.bind("<KeyRelease>", self._on_name_typed)

        for column, (text, command, width) in enumerate((
            ("New", self._on_new, 70),
            ("Open...", self._on_open, 90),
            ("Save", self._on_save, 80),
            ("Save As...", self._on_save_as, 100),
        ), start=2):
            ctk.CTkButton(
                file_row, text=text, width=width, height=32, command=command,
                fg_color="transparent", border_width=1, text_color=MUTED,
            ).grid(row=0, column=column, padx=(8, 0))

        # --- tool row ---------------------------------------------------
        tool_row = ctk.CTkFrame(self, fg_color="transparent")
        tool_row.grid(row=1, column=0, sticky="ew", padx=6, pady=(10, 0))
        tool_row.grid_columnconfigure(6, weight=1)

        ctk.CTkButton(
            tool_row, text="+ Step", width=90, height=34,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=lambda: self._add_node("process"),
        ).grid(row=0, column=0)

        ctk.CTkButton(
            tool_row, text="+ Decision", width=105, height=34,
            font=ctk.CTkFont(size=13, weight="bold"), fg_color="#c79100",
            hover_color="#a87c00", command=lambda: self._add_node("decision"),
        ).grid(row=0, column=1, padx=(8, 0))

        ctk.CTkButton(
            tool_row, text="+ Start", width=80, height=34,
            fg_color="transparent", border_width=1, text_color=MUTED,
            command=lambda: self._add_node("start"),
        ).grid(row=0, column=2, padx=(8, 0))

        ctk.CTkButton(
            tool_row, text="+ End", width=75, height=34,
            fg_color="transparent", border_width=1, text_color=MUTED,
            command=lambda: self._add_node("end"),
        ).grid(row=0, column=3, padx=(8, 0))

        self.connect_switch = ctk.CTkSwitch(
            tool_row, text="Connect mode", command=self._on_connect_toggled,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.connect_switch.grid(row=0, column=4, padx=(20, 0))

        self.edit_button = ctk.CTkButton(
            tool_row, text="Edit node", width=95, height=34,
            fg_color="transparent", border_width=1, text_color=MUTED,
            command=self._on_edit_selected,
        )
        self.edit_button.grid(row=0, column=7, padx=(8, 0))

        self.delete_button = ctk.CTkButton(
            tool_row, text="Delete", width=80, height=34,
            fg_color="transparent", border_width=1, text_color=MUTED,
            command=self._on_delete_selected,
        )
        self.delete_button.grid(row=0, column=8, padx=(8, 0))

        # --- canvas -----------------------------------------------------
        self.canvas = FlowchartCanvas(
            self, chart=self.chart,
            on_edit=self._edit_node,
            on_open_ref=self._open_reference,
            on_select=self._update_selection_controls,
            on_change=self._mark_dirty,
            on_status=self.set_status,
        )
        self.canvas.grid(row=2, column=0, sticky="nsew", padx=6, pady=(10, 4))

        # --- hint bar ---------------------------------------------------
        self.hint_label = ctk.CTkLabel(
            self, anchor="w", justify="left", text_color=MUTED,
            font=ctk.CTkFont(size=11),
            text="Double-click a node to edit it. Click its page reference to "
                 "open that page. Right-drag to pan. Delete removes the "
                 "selection. Organisational only - no values are calculated.",
        )
        self.hint_label.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 6))

    # ------------------------------------------------------------------
    # Title / dirty state
    # ------------------------------------------------------------------
    def _update_title(self) -> None:
        self.name_entry.delete(0, "end")
        self.name_entry.insert(0, self.chart.name)

    def _mark_dirty(self) -> None:
        self.dirty = True

    def _on_name_typed(self, _event=None) -> None:
        name = self.name_entry.get().strip() or "Untitled workflow"
        if name != self.chart.name:
            self.chart.name = name
            self.chart.touch()
            self.dirty = True

    def _confirm_discard(self, action: str) -> bool:
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel(
            "Unsaved changes",
            f"'{self.chart.name}' has unsaved changes.\n\n"
            f"Save before {action}?",
            parent=self,
        )
        if answer is None:
            return False
        if answer:
            return self._on_save()
        return True

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------
    def _add_node(self, kind: str) -> None:
        if self.connect_switch.get():
            # Adding a node mid-connection would be confusing; drop out first.
            self.connect_switch.deselect()
            self._on_connect_toggled()

        node = self.canvas.add_node(kind)
        if edit_node(self, node, self.indexer.list_documents()):
            self._mark_dirty()
            self.set_status(f"Added '{node.display_title}'.")
        else:
            # Cancelling the editor on a brand-new node should not leave an
            # empty box behind.
            self.chart.remove_node(node.id)
            self.canvas.selected_node = None
            self.set_status("Cancelled - no node added.")
        self.canvas.redraw()
        self._update_selection_controls(self.canvas.selected())

    def _edit_node(self, node: FlowNode) -> None:
        if edit_node(self, node, self.indexer.list_documents()):
            self.chart.touch()
            self._mark_dirty()
            self.canvas.redraw()
            self._update_selection_controls(node)
            self.set_status(f"Updated '{node.display_title}'.")

    def _on_edit_selected(self) -> None:
        node = self.canvas.selected()
        if node is None:
            self.set_status("Select a node first, then choose Edit node.")
            return
        self._edit_node(node)

    def _on_delete_selected(self) -> None:
        if self.canvas.selected() is None and self.canvas.selected_edge is None:
            self.set_status("Select a node or a connection to delete it.")
            return
        self.canvas.delete_selection()
        self._update_selection_controls(None)

    def _update_selection_controls(self, node: Optional[FlowNode]) -> None:
        state = "normal" if node is not None else "disabled"
        self.edit_button.configure(state=state)
        has_selection = node is not None or self.canvas.selected_edge is not None
        self.delete_button.configure(state="normal" if has_selection else "disabled")

    def _on_connect_toggled(self) -> None:
        enabled = bool(self.connect_switch.get())
        self.canvas.set_connect_mode(enabled)
        if not enabled:
            self.set_status("Connect mode off.")

    # ------------------------------------------------------------------
    # Opening a reference
    # ------------------------------------------------------------------
    def _open_reference(self, node: FlowNode) -> None:
        """Requirement 3: a node's reference opens that exact page."""
        ref = node.ref
        if ref is None:
            return

        path = resolve_document_path(ref, self.indexer.list_documents())
        if path is None:
            if not messagebox.askyesno(
                "PDF not found",
                f"'{node.display_title}' points at:\n\n"
                f"    {ref.document_title}\n    {ref.label}\n\n"
                f"That PDF is not where this workflow expects it "
                f"({ref.file_path or 'no path recorded'}).\n\n"
                f"Locate it now?",
                parent=self,
            ):
                return
            chosen = filedialog.askopenfilename(
                title=f"Locate '{ref.document_title}'",
                filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
            )
            if not chosen:
                return
            # Remember it, so a shared workflow only asks once per machine.
            ref.file_path = str(Path(chosen))
            self.chart.touch()
            self._mark_dirty()
            path = Path(chosen)

        self.preview.open(
            path, page_number=ref.page_number, label=ref.label,
            document_id=ref.document_id,
        )

    # ------------------------------------------------------------------
    # Files
    # ------------------------------------------------------------------
    def _on_new(self) -> None:
        if not self._confirm_discard("starting a new workflow"):
            return
        self.chart = Flowchart()
        self.file_path = None
        self.dirty = False
        self.canvas.set_chart(self.chart)
        self._update_title()
        self._update_selection_controls(None)
        self.set_status("New workflow. " + DISCLAIMER)

    def _on_open(self) -> None:
        if not self._confirm_discard("opening another workflow"):
            return
        chosen = filedialog.askopenfilename(
            title="Open a flowchart", filetypes=FILE_TYPES,
        )
        if not chosen:
            return
        try:
            chart = Flowchart.load_json(Path(chosen))
        except FlowchartError as exc:
            messagebox.showerror("Could not open flowchart", str(exc), parent=self)
            self.set_status(f"Could not open {Path(chosen).name}: {exc}")
            return

        self.chart = chart
        self.file_path = Path(chosen)
        self.dirty = False
        self.canvas.set_chart(chart)
        self._update_title()
        self._update_selection_controls(None)
        self.set_status(
            f"Opened '{chart.name}': {len(chart.nodes)} nodes, "
            f"{len(chart.edges)} connections. {DISCLAIMER}"
        )

    def _on_save(self) -> bool:
        if self.file_path is None:
            return self._on_save_as()
        return self._write(self.file_path)

    def _on_save_as(self) -> bool:
        suggested = (self.chart.name or "workflow").strip().replace(" ", "_")
        chosen = filedialog.asksaveasfilename(
            title="Save flowchart", defaultextension=".json",
            initialfile=f"{suggested}.json", filetypes=FILE_TYPES,
        )
        if not chosen:
            return False
        return self._write(Path(chosen))

    def _write(self, path: Path) -> bool:
        self._on_name_typed()
        try:
            saved = self.chart.save_json(path)
        except OSError as exc:
            messagebox.showerror("Could not save", str(exc), parent=self)
            self.set_status(f"Could not save: {exc}")
            return False
        self.file_path = saved
        self.dirty = False
        self.set_status(f"Saved to {saved.name}.")
        return True

    # ------------------------------------------------------------------
    # Shell hooks
    # ------------------------------------------------------------------
    def on_resize(self) -> None:
        """Hook for the shell's <Configure> handler."""
        self.hint_label.configure(wraplength=max(320, self.winfo_width() - 40))
