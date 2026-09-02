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
from .menu_bar import MenuBar, MenuItem
from .smooth_scroll import SmoothScroller, smooth_scroll
from .guide_dialog import GuideDialog, show_guide
from .settings_dialog import (
    SettingsDialog, apply_settings, edit_settings,
)
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
    "MenuBar",
    "MenuItem",
    "SmoothScroller",
    "smooth_scroll",
    "GuideDialog",
    "show_guide",
    "SettingsDialog",
    "edit_settings",
    "apply_settings",
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
