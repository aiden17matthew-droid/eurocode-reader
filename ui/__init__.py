"""CustomTkinter user interface for EuroCode Compass."""

from .main_window import EurocodeReaderApp
from .search_view import SearchView
from .flowchart_view import FlowchartView
from .flowchart_canvas import FlowchartCanvas
from .node_editor import NodeEditorDialog, edit_node
from .edge_label_dialog import EdgeLabelDialog, ask_edge_label
from .equation_editor import (
    EquationEditorDialog, edit_equation, manage_equations,
)
from .about_dialog import AboutDialog, show_about
from . import equation_render
from .workspace_bar import WorkspaceBar
from .services import AsyncRunner, PreviewManager, reflow_row
from .preview_window import PagePreviewWindow, open_in_system_viewer
from .result_card import ResultCard

__all__ = [
    "EurocodeReaderApp",
    "SearchView",
    "FlowchartView",
    "FlowchartCanvas",
    "NodeEditorDialog",
    "edit_node",
    "EdgeLabelDialog",
    "EquationEditorDialog",
    "edit_equation",
    "manage_equations",
    "AboutDialog",
    "show_about",
    "equation_render",
    "ask_edge_label",
    "WorkspaceBar",
    "AsyncRunner",
    "reflow_row",
    "PreviewManager",
    "PagePreviewWindow",
    "open_in_system_viewer",
    "ResultCard",
]
