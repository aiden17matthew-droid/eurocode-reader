"""Application shell for the Eurocode Reader.

Holds the persistent header (title + liability notice), the workspace bar, the
tab view, and the status bar. The tabs themselves are self-contained views:

    SearchView      Phase 1 - load a PDF, index it offline, find the clause
    FlowchartView   Phase 2 - build design workflows that point at clauses

Both share one Indexer, one AsyncRunner and one PreviewManager, so a clause
opens the same way whichever tab asked for it. A workspace spans both, so the
shell is where saving and loading one lives.

The app is an index/compass. It points at clauses, tables and pages; it never
calculates, interprets or suggests design changes.
"""

from __future__ import annotations

import traceback
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import List, Optional

import customtkinter as ctk

from backend.equations import EquationLibrary
from backend.indexer import DISCLAIMER, Indexer, SearchHit
from backend.workspace import (
    Workspace,
    WorkspaceError,
    clear_session,
    load_session,
    plan_restore,
    resolve_document_ids,
    resolve_selected_id,
    save_session,
)

from .flowchart_view import FlowchartView
from .search_view import SearchView
from .services import AsyncRunner, PreviewManager
from .workspace_bar import WorkspaceBar

TAB_SEARCH = "Search"
TAB_FLOWCHART = "Flowchart Builder"

WORKSPACE_FILE_TYPES = [("Workspace JSON", "*.json"), ("All files", "*.*")]

ACCENT = "#3b8ed0"
WARNING = "#e0a800"
MUTED = "#8a8a8a"


class EurocodeReaderApp(ctk.CTk):
    def __init__(
        self,
        indexer: Optional[Indexer] = None,
        session_path: Optional[Path] = None,
        resume: bool = True,
    ) -> None:
        super().__init__()

        self.indexer = indexer or Indexer()
        # One global equation library, shared by every workflow the engineer
        # ever opens - an expression is typed once, not once per project.
        self.equation_library = EquationLibrary.load_or_empty()
        self.session_path = session_path
        self.workspace_path: Optional[Path] = None
        self.workspace_name = "Untitled workspace"
        self.workspace_dirty = False

        self.title("Eurocode Reader - offline clause finder")
        self.geometry("980x820")
        self.minsize(760, 600)

        self.runner = AsyncRunner(self, on_error=self._default_error)
        self.preview = PreviewManager(
            self,
            indexer=self.indexer,
            on_status=self.set_status,
            # The search tab owns the document list, so a relocated PDF has to
            # be reflected there.
            on_relocated=lambda doc_id: self.search_view.refresh_document_list(
                select_id=doc_id
            ),
        )

        self._build_layout()
        self.runner.start()
        self._warm_up_model()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Configure>", self._on_resize)

        if resume:
            # After the window exists, so progress and status are visible.
            self.after(120, self.resume_session)
        else:
            self._refresh_workspace_bar()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # --- header (persistent across every tab) -----------------------
        header = ctk.CTkFrame(self, corner_radius=0, fg_color=("#e8e8e8", "#212121"))
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header, text="Eurocode Reader",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(14, 0))

        ctk.CTkLabel(
            header,
            text="Search your own Eurocode PDFs offline. "
                 "Results point to a page and clause - nothing more.",
            font=ctk.CTkFont(size=12), text_color=MUTED, anchor="w",
        ).grid(row=1, column=0, sticky="w", padx=20, pady=(0, 4))

        # Liability notice - above the tabs, so it is visible on all of them,
        # always visible, never dismissible.
        ctk.CTkLabel(
            header, text="  " + DISCLAIMER + "  ",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#3d2f00", fg_color=WARNING, corner_radius=6,
        ).grid(row=2, column=0, sticky="w", padx=20, pady=(0, 14))

        # --- workspace bar ----------------------------------------------
        self.workspace_bar = WorkspaceBar(
            self,
            on_load=self.load_workspace,
            on_save=self.save_workspace,
            on_save_as=self.save_workspace_as,
        )
        self.workspace_bar.grid(row=1, column=0, sticky="ew", padx=20, pady=(10, 0))

        # --- tabs -------------------------------------------------------
        self.tabs = ctk.CTkTabview(self, corner_radius=8)
        self.tabs.grid(row=2, column=0, sticky="nsew", padx=14, pady=(10, 6))
        self.tabs.add(TAB_SEARCH)
        self.tabs.add(TAB_FLOWCHART)

        for name in (TAB_SEARCH, TAB_FLOWCHART):
            tab = self.tabs.tab(name)
            tab.grid_columnconfigure(0, weight=1)
            tab.grid_rowconfigure(0, weight=1)

        self.search_view = SearchView(
            self.tabs.tab(TAB_SEARCH),
            indexer=self.indexer, runner=self.runner,
            preview=self.preview, set_status=self.set_status,
            on_add_to_flowchart=self.add_hit_to_flowchart,
            on_documents_changed=self.mark_workspace_dirty,
        )
        self.search_view.grid(row=0, column=0, sticky="nsew")

        self.flowchart_view = FlowchartView(
            self.tabs.tab(TAB_FLOWCHART),
            indexer=self.indexer, runner=self.runner,
            preview=self.preview, set_status=self.set_status,
            on_dirty=self.mark_workspace_dirty,
            equation_library=self.equation_library,
        )
        self.flowchart_view.grid(row=0, column=0, sticky="nsew")

        self.tabs.set(TAB_SEARCH)

        # --- status bar -------------------------------------------------
        self.status_label = ctk.CTkLabel(
            self, text="Ready.", font=ctk.CTkFont(size=11),
            text_color=MUTED, anchor="w",
        )
        self.status_label.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 10))

    def set_status(self, text: str) -> None:
        self.status_label.configure(text=text)

    # ------------------------------------------------------------------
    # Cross-tab actions
    # ------------------------------------------------------------------
    def add_hit_to_flowchart(self, hit: SearchHit) -> None:
        """Search result -> flowchart step, switching tabs on the way.

        The shell owns both tabs, so this is where the two are joined rather
        than either view reaching into the other.
        """
        self.tabs.set(TAB_FLOWCHART)
        self.flowchart_view.add_node_from_hit(hit)

    # ------------------------------------------------------------------
    # Workspaces
    #
    # Every write below happens because the engineer clicked something. The
    # only file this app writes on its own is the private session file in
    # data/, which is never one of their saved workspaces - so a bad
    # afternoon can never overwrite a good rollback point.
    # ------------------------------------------------------------------
    def capture_workspace(self, name: Optional[str] = None) -> Workspace:
        """Snapshot the live state: indexed documents plus the open chart."""
        return Workspace.from_state(
            name=name or self.workspace_name,
            documents=self.indexer.list_documents(),
            flowchart=self.flowchart_view.chart,
            flowchart_path=self.flowchart_view.file_path,
            selected_document_title=self.search_view.selected_document_title(),
        )

    def mark_workspace_dirty(self) -> None:
        self.workspace_dirty = True
        self._refresh_workspace_bar()

    def _refresh_workspace_bar(self) -> None:
        documents = len(self.indexer.list_documents())
        nodes = len(self.flowchart_view.chart.nodes)
        detail = f"{documents} document(s), {nodes} flowchart node(s)"
        if self.workspace_path is None:
            self.workspace_bar.set_workspace(
                None,
                detail + " - not saved to a workspace yet",
            )
        else:
            self.workspace_bar.set_workspace(
                self.workspace_name, detail, unsaved=self.workspace_dirty
            )

    def save_workspace(self) -> bool:
        """Save over the open workspace, or ask where to put a new one."""
        if self.workspace_path is None:
            return self.save_workspace_as()
        return self._write_workspace(self.workspace_path)

    def save_workspace_as(self) -> bool:
        suggested = (self.workspace_name or "workspace").strip().replace(" ", "_")
        chosen = filedialog.asksaveasfilename(
            title="Save workspace as", defaultextension=".json",
            initialfile=f"{suggested}.json", filetypes=WORKSPACE_FILE_TYPES,
        )
        if not chosen:
            return False
        return self._write_workspace(Path(chosen), rename=True)

    def _write_workspace(self, path: Path, rename: bool = False) -> bool:
        name = path.stem if rename else self.workspace_name
        workspace = self.capture_workspace(name=name)
        try:
            saved = workspace.save_json(path)
        except OSError as exc:
            messagebox.showerror("Could not save workspace", str(exc), parent=self)
            self.set_status(f"Could not save the workspace: {exc}")
            return False

        self.workspace_path = saved
        self.workspace_name = name
        self.workspace_dirty = False
        self._refresh_workspace_bar()
        self.set_status(
            f"Saved workspace '{name}' ({workspace.summary}) to {saved.name}. "
            f"{DISCLAIMER}"
        )
        return True

    def load_workspace(self) -> None:
        if not self._confirm_discard():
            return
        chosen = filedialog.askopenfilename(
            title="Load workspace", filetypes=WORKSPACE_FILE_TYPES,
        )
        if not chosen:
            return
        try:
            workspace = Workspace.load_json(Path(chosen))
        except WorkspaceError as exc:
            messagebox.showerror("Could not load workspace", str(exc), parent=self)
            self.set_status(f"Could not load {Path(chosen).name}: {exc}")
            return
        self.restore_workspace(workspace, Path(chosen), interactive=True)

    def _confirm_discard(self) -> bool:
        """A workspace load replaces the canvas, so unsaved work is at risk."""
        if not self.flowchart_view.has_unsaved_changes():
            return True
        answer = messagebox.askyesnocancel(
            "Unsaved flowchart",
            f"'{self.flowchart_view.chart.name}' has unsaved changes that "
            f"loading a workspace will replace.\n\nSave the flowchart first?",
            parent=self,
        )
        if answer is None:
            return False
        if answer:
            return bool(self.flowchart_view._on_save())
        return True

    def restore_workspace(
        self,
        workspace: Workspace,
        path: Optional[Path],
        interactive: bool = True,
        source: str = "Loaded workspace",
    ) -> None:
        """Bring the app back to a saved state.

        Documents already in the index are left alone; ones the index has
        never seen are re-indexed from the engineer's own PDFs. Nothing is
        downloaded and no PDF is ever copied.
        """
        plan = plan_restore(workspace, self.indexer.list_documents())

        if plan.missing and interactive:
            names = "\n".join(f"    {d.title}\n        {d.file_path}"
                              for d in plan.missing)
            if not messagebox.askyesno(
                "Some PDFs are missing",
                f"'{workspace.name}' refers to {len(plan.missing)} PDF(s) that "
                f"are not where the workspace expects them:\n\n{names}\n\n"
                f"Load the rest of the workspace anyway?",
                parent=self,
            ):
                return

        if plan.to_index:
            self.tabs.set(TAB_SEARCH)      # so the progress bar is visible
            paths = [Path(d.file_path) for d in plan.to_index]
            self.set_status(
                f"Restoring '{workspace.name}': indexing "
                f"{len(paths)} document(s) not yet in the local index..."
            )
            self.search_view.index_documents(
                paths,
                on_done=lambda problems: self._finish_restore(
                    workspace, path, plan, problems, source
                ),
            )
            return

        self._finish_restore(workspace, path, plan, [], source)

    def _finish_restore(
        self,
        workspace: Workspace,
        path: Optional[Path],
        plan,
        problems: List[str],
        source: str = "Loaded workspace",
    ) -> None:
        self.flowchart_view.adopt_chart(
            workspace.flowchart, workspace.flowchart_path
        )

        # Point the search dropdown at what was just restored. Leaving it on
        # whatever happened to be selected means the engineer has to hunt for
        # their own Eurocode again straight after loading it.
        #
        #   1. the document the workspace was searching, if it is here
        #   2. otherwise the only document, when there is just one
        #   3. otherwise All Loaded Documents, which searches every one
        documents = self.indexer.list_documents()
        restored = resolve_document_ids(workspace, documents)
        select_id = resolve_selected_id(workspace, documents)
        if select_id is None and len(restored) == 1:
            select_id = restored[0]
        self.search_view.refresh_document_list(select_id=select_id)

        self.workspace_path = path
        self.workspace_name = workspace.name
        self.workspace_dirty = False
        self._refresh_workspace_bar()

        # "Loaded workspace 'X'" is wrong for an automatic resume - the
        # engineer did not load anything, the app just picked up where they
        # left off.
        headline = (f"{source} ({plan.describe()})" if path is None
                    else f"{source} '{workspace.name}' ({plan.describe()})")
        notes = [headline]
        if plan.missing:
            notes.append(
                f"{len(plan.missing)} PDF(s) could not be found - "
                f"load them again from the Search tab"
            )
        if problems:
            notes.append(f"{len(problems)} failed to index")
        if restored:
            notes.append(
                f"searching {self.search_view.selected_document_label()}"
            )
        self.set_status(". ".join(notes) + f". {DISCLAIMER}")

        if problems:
            messagebox.showwarning(
                "Some documents could not be indexed",
                "\n\n".join(problems), parent=self,
            )

    # ------------------------------------------------------------------
    # Session resume (never writes to a named workspace)
    # ------------------------------------------------------------------
    def resume_session(self) -> None:
        """Reopen last night's state so the PDFs do not need remounting."""
        try:
            workspace, path = (load_session(self.session_path)
                               if self.session_path is not None
                               else load_session())
        except Exception:                       # a bad session file must never
            traceback.print_exc()               # stop the app from starting
            workspace, path = None, None

        if workspace is None:
            self._refresh_workspace_bar()
            self.set_status(
                "Ready. Load a Eurocode PDF, then use Save Workspace As... "
                "to create a project state you can return to."
            )
            return

        # Non-interactive: nobody wants a modal dialog at breakfast because a
        # PDF moved. Anything missing is reported in the status bar instead.
        self.restore_workspace(
            workspace, path, interactive=False,
            source="Resumed your last session",
        )

    def _save_session(self) -> None:
        try:
            workspace = self.capture_workspace()
            if self.session_path is not None:
                save_session(workspace, self.workspace_path, self.session_path)
            else:
                save_session(workspace, self.workspace_path)
        except Exception:               # quitting must never fail because of
            traceback.print_exc()       # a session file

    def _default_error(self, exc: Exception) -> None:
        self.set_status(f"Error: {exc}")
        messagebox.showerror("Eurocode Reader", str(exc), parent=self)

    # ------------------------------------------------------------------
    # Model warm-up
    # ------------------------------------------------------------------
    def _warm_up_model(self) -> None:
        """Load the local model in the background so the first search is fast."""
        self.set_status("Loading local AI model...")

        self.runner.run(
            work=lambda: self.indexer.embedder.warm_up(),
            on_done=lambda _r: self.set_status(
                "Local model ready. Offline - no internet required."
            ),
            on_error=lambda exc: self.set_status(f"Model not available: {exc}"),
        )

    # ------------------------------------------------------------------
    # Window events
    # ------------------------------------------------------------------
    def _on_resize(self, event) -> None:
        if event.widget is not self:
            return
        self.search_view.on_resize()
        self.flowchart_view.on_resize()
        self.workspace_bar.reflow()

    def _on_close(self) -> None:
        self._save_session()
        self.runner.stop()
        self.preview.close()
        self.indexer.close()
        self.destroy()
