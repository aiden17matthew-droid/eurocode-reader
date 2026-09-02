"""Edit one flowchart node: its title, the engineer's notes, the equation it
displays, and the Eurocode page or clause it points at.

Nothing typed in this dialog is ever evaluated. There is no field for a
variable's value, a unit, a substitution or a result; the equation is stored
as LaTeX and only ever handed to a typesetter to be drawn. Notes are the
engineer's own instructions to themselves and their colleagues.
"""

from __future__ import annotations

from tkinter import messagebox
from typing import Dict, List, Optional

import customtkinter as ctk

from backend.equations import EquationLibrary, NOT_CALCULATED
from backend.flowchart import (
    MAX_NOTES, MAX_TITLE, FlowNode, NodeEquation, NodeRef,
)
from backend.indexer import DISCLAIMER

from .equation_editor import edit_equation
from .equation_render import (
    EquationRenderError, blank_ctk_image, render_ctk_image,
)

NO_REFERENCE = "(no Eurocode reference)"
NO_EQUATION = "(no equation)"

EQUATION_PREVIEW_HEIGHT = 40

KIND_CHOICES = {
    "Step / Process": "process",
    "Decision (If / Else)": "decision",
    "Start": "start",
    "End": "end",
}
KIND_LOOKUP = {v: k for k, v in KIND_CHOICES.items()}

MUTED = "#8a8a8a"
ACCENT = "#3b8ed0"
WARNING = "#e0a800"


class NodeEditorDialog(ctk.CTkToplevel):
    """Modal editor for a single node. ``saved`` says whether it was applied."""

    def __init__(
        self,
        master,
        node: FlowNode,
        documents: List[dict],
        library: Optional[EquationLibrary] = None,
    ) -> None:
        super().__init__(master)

        self.node = node
        self.saved = False
        self._documents = documents or []
        self._doc_labels: Dict[str, Optional[dict]] = {NO_REFERENCE: None}
        self.library = library if library is not None else EquationLibrary()
        self._equation: Optional[NodeEquation] = node.equation
        self._equation_photo = None          # Tk drops uncited images
        self._blank = blank_ctk_image()

        self.title(f"Edit node - {node.display_title}")
        self.geometry("580x820")
        self.minsize(500, 640)
        self.resizable(True, True)

        self._build_layout()
        self._load_from_node()

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.bind("<Escape>", lambda _e: self._on_cancel())

        self.transient(master)
        self.after(80, self._focus_first)

    def _focus_first(self) -> None:
        try:
            self.grab_set()
            self.lift()
            self.title_entry.focus_set()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.grid(row=0, column=0, sticky="nsew", padx=16, pady=(14, 0))
        body.grid_columnconfigure(0, weight=1)

        row = 0

        ctk.CTkLabel(body, text="Node type", anchor="w",
                     font=ctk.CTkFont(size=12, weight="bold")
                     ).grid(row=row, column=0, sticky="ew")
        row += 1
        self.kind_menu = ctk.CTkOptionMenu(
            body, values=list(KIND_CHOICES.keys()), height=34,
        )
        self.kind_menu.grid(row=row, column=0, sticky="ew", pady=(4, 14))
        row += 1

        ctk.CTkLabel(body, text="Title", anchor="w",
                     font=ctk.CTkFont(size=12, weight="bold")
                     ).grid(row=row, column=0, sticky="ew")
        row += 1
        self.title_entry = ctk.CTkEntry(
            body, height=38, font=ctk.CTkFont(size=13),
            placeholder_text="e.g. Check imposed load category",
        )
        self.title_entry.grid(row=row, column=0, sticky="ew", pady=(4, 14))
        row += 1

        ctk.CTkLabel(body, text="Your notes / instructions", anchor="w",
                     font=ctk.CTkFont(size=12, weight="bold")
                     ).grid(row=row, column=0, sticky="ew")
        row += 1
        ctk.CTkLabel(
            body, anchor="w", justify="left", text_color=MUTED,
            font=ctk.CTkFont(size=11), wraplength=460,
            text="Free text, for you and your colleagues. Nothing written here "
                 "is calculated, checked or evaluated by the app.",
        ).grid(row=row, column=0, sticky="ew", pady=(2, 4))
        row += 1
        self.notes_box = ctk.CTkTextbox(body, height=150, font=ctk.CTkFont(size=12))
        self.notes_box.grid(row=row, column=0, sticky="ew", pady=(0, 14))
        row += 1

        # --- equation ----------------------------------------------------
        equation_frame = ctk.CTkFrame(body)
        equation_frame.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        equation_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            equation_frame, text="Equation", anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 2))

        ctk.CTkLabel(
            equation_frame, anchor="w", justify="left", text_color=MUTED,
            font=ctk.CTkFont(size=11), wraplength=430,
            text="Shown on the node for whoever reads the chart. "
                 + NOT_CALCULATED,
        ).grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 8))

        self.equation_menu = ctk.CTkOptionMenu(
            equation_frame, values=[NO_EQUATION], height=32,
            command=self._on_equation_chosen,
        )
        self.equation_menu.grid(row=2, column=0, sticky="ew", padx=(12, 8))

        ctk.CTkButton(
            equation_frame, text="Build / edit...", width=120, height=32,
            fg_color="transparent", border_width=1, text_color=ACCENT,
            command=self._on_build_equation,
        ).grid(row=2, column=1, sticky="e", padx=(0, 12))

        self.equation_preview = ctk.CTkLabel(
            equation_frame, text="", height=EQUATION_PREVIEW_HEIGHT + 12,
            fg_color=("#ffffff", "#2b2f34"), corner_radius=6,
        )
        self.equation_preview.grid(row=3, column=0, columnspan=2, sticky="ew",
                                   padx=12, pady=(10, 12))
        row += 1

        # --- Eurocode reference ----------------------------------------
        ref_frame = ctk.CTkFrame(body)
        ref_frame.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        ref_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            ref_frame, text="Eurocode reference", anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 2))

        ctk.CTkLabel(
            ref_frame, anchor="w", justify="left", text_color=MUTED,
            font=ctk.CTkFont(size=11), wraplength=430,
            text="Points this step at a page in one of your indexed PDFs. "
                 "Clicking it on the canvas opens that page.",
        ).grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 8))

        ctk.CTkLabel(ref_frame, text="Document", anchor="w", text_color=MUTED
                     ).grid(row=2, column=0, sticky="w", padx=(12, 8), pady=4)
        self.doc_menu = ctk.CTkOptionMenu(
            ref_frame, values=[NO_REFERENCE], height=32,
            command=self._on_document_changed,
        )
        self.doc_menu.grid(row=2, column=1, sticky="ew", padx=(0, 12), pady=4)

        ctk.CTkLabel(ref_frame, text="Page", anchor="w", text_color=MUTED
                     ).grid(row=3, column=0, sticky="w", padx=(12, 8), pady=4)
        self.page_entry = ctk.CTkEntry(ref_frame, height=32,
                                       placeholder_text="e.g. 20")
        self.page_entry.grid(row=3, column=1, sticky="ew", padx=(0, 12), pady=4)

        ctk.CTkLabel(ref_frame, text="Clause", anchor="w", text_color=MUTED
                     ).grid(row=4, column=0, sticky="w", padx=(12, 8), pady=4)
        self.clause_entry = ctk.CTkEntry(ref_frame, height=32,
                                         placeholder_text="optional, e.g. 6.3")
        self.clause_entry.grid(row=4, column=1, sticky="ew", padx=(0, 12), pady=4)

        ctk.CTkLabel(ref_frame, text="Table / Figure", anchor="w", text_color=MUTED
                     ).grid(row=5, column=0, sticky="w", padx=(12, 8), pady=4)
        self.table_entry = ctk.CTkEntry(ref_frame, height=32,
                                        placeholder_text="optional, e.g. Table 6.1")
        self.table_entry.grid(row=5, column=1, sticky="ew", padx=(0, 12), pady=4)

        self.page_hint = ctk.CTkLabel(
            ref_frame, text="", anchor="w", text_color=MUTED,
            font=ctk.CTkFont(size=11),
        )
        self.page_hint.grid(row=6, column=0, columnspan=2, sticky="ew",
                            padx=12, pady=(2, 12))
        row += 1

        # --- footer -----------------------------------------------------
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=1, column=0, sticky="ew", padx=16, pady=(6, 12))
        footer.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            footer, text="  " + DISCLAIMER + "  ",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#3d2f00", fg_color=WARNING, corner_radius=6,
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        ctk.CTkButton(
            footer, text="Cancel", width=100, height=36,
            fg_color="transparent", border_width=1, text_color=MUTED,
            command=self._on_cancel,
        ).grid(row=1, column=0, sticky="e", padx=(0, 8))

        ctk.CTkButton(
            footer, text="Save", width=120, height=36,
            font=ctk.CTkFont(size=13, weight="bold"), command=self._on_save,
        ).grid(row=1, column=1, sticky="e")

    # ------------------------------------------------------------------
    # Populate / read back
    # ------------------------------------------------------------------
    def refresh_equation_list(self) -> None:
        """Rebuild the equation picker from the global library."""
        names = self.library.names()
        values = [NO_EQUATION] + names

        # An equation the node already carries may not be in this machine's
        # library - a shared workflow, or one never saved. Offer it anyway.
        current = self._equation
        if current is not None and current.display_name not in names:
            values.append(current.display_name)

        self.equation_menu.configure(values=values)
        self.equation_menu.set(
            current.display_name if current is not None else NO_EQUATION
        )
        self._draw_equation_preview()

    def _draw_equation_preview(self) -> None:
        equation = self._equation
        if equation is None:
            self._clear_equation_preview("No equation", MUTED)
            return
        colour = "#f0f0f0" if ctk.get_appearance_mode() == "Dark" else "#101418"
        try:
            photo = render_ctk_image(equation.latex,
                                     px_height=EQUATION_PREVIEW_HEIGHT,
                                     color=colour)
        except EquationRenderError as exc:
            self._clear_equation_preview(f"Will not draw: {exc}", WARNING)
            return
        self._equation_photo = photo
        self.equation_preview.configure(image=photo, text="")

    def _clear_equation_preview(self, text: str, colour: str) -> None:
        """Take the picture off the label before letting it go.

        Releasing it first destroys the underlying Tk image while the label
        still refers to it, and reconfiguring the label then fails.
        """
        self.equation_preview.configure(image=self._blank, text=text,
                                        text_color=colour)
        self._equation_photo = None

    def _on_equation_chosen(self, name: str) -> None:
        if name == NO_EQUATION:
            self._equation = None
            self._draw_equation_preview()
            return
        saved = self.library.by_name(name)
        if saved is not None:
            self._equation = NodeEquation(latex=saved.latex, name=saved.name)
        self._draw_equation_preview()

    def _on_build_equation(self) -> None:
        seed = None
        if self._equation is not None:
            saved = self.library.by_name(self._equation.name)
            from backend.equations import Equation
            seed = saved or Equation(
                name=self._equation.name or "Equation",
                latex=self._equation.latex,
            )
        chosen = edit_equation(self, self.library, initial=seed,
                               on_library_changed=self.refresh_equation_list)
        if chosen is not None:
            self._equation = NodeEquation(latex=chosen.latex, name=chosen.name)
        self.refresh_equation_list()

    def _load_from_node(self) -> None:
        self.kind_menu.set(KIND_LOOKUP.get(self.node.kind, "Step / Process"))
        self.title_entry.insert(0, self.node.title)
        if self.node.notes:
            self.notes_box.insert("1.0", self.node.notes)

        self._doc_labels = {NO_REFERENCE: None}
        for doc in self._documents:
            label = f"{doc['title']} ({doc['page_count']} pp)"
            if label in self._doc_labels:
                label = f"{label} [{doc['id']}]"
            self._doc_labels[label] = doc

        self.doc_menu.configure(values=list(self._doc_labels.keys()))

        ref = self.node.ref
        selected = NO_REFERENCE
        if ref is not None:
            for label, doc in self._doc_labels.items():
                if doc is None:
                    continue
                if (ref.document_id is not None and int(doc["id"]) == ref.document_id) \
                        or str(doc["title"]) == ref.document_title:
                    selected = label
                    break
            else:
                # The flowchart came from another machine and that standard is
                # not indexed here. Keep the pointer rather than silently
                # dropping it.
                label = f"{ref.document_title} (not indexed here)"
                self._doc_labels[label] = {
                    "id": ref.document_id, "title": ref.document_title,
                    "file_path": ref.file_path, "page_count": 0,
                }
                self.doc_menu.configure(values=list(self._doc_labels.keys()))
                selected = label

            self.page_entry.insert(0, str(ref.page_number))
            if ref.clause_ref:
                self.clause_entry.insert(0, ref.clause_ref)
            if ref.table_ref:
                self.table_entry.insert(0, ref.table_ref)

        self.doc_menu.set(selected)
        self._on_document_changed(selected)
        self.refresh_equation_list()

    def _on_document_changed(self, label: str) -> None:
        doc = self._doc_labels.get(label)
        state = "disabled" if doc is None else "normal"
        for widget in (self.page_entry, self.clause_entry, self.table_entry):
            widget.configure(state=state)

        if doc is None:
            self.page_hint.configure(text="No page will be attached to this node.")
        elif int(doc.get("page_count") or 0) > 0:
            self.page_hint.configure(
                text=f"This document has {doc['page_count']} pages."
            )
        else:
            self.page_hint.configure(
                text="This document is not in your local index - the page will "
                     "be kept, but you will be asked to locate the PDF."
            )

    def _read_reference(self) -> Optional[NodeRef]:
        """Build the NodeRef, or raise ValueError with a message for the user."""
        label = self.doc_menu.get()
        doc = self._doc_labels.get(label)
        if doc is None:
            return None

        raw_page = self.page_entry.get().strip()
        if not raw_page:
            raise ValueError(
                "Enter the page number this step points to, "
                "or set the document back to '(no Eurocode reference)'."
            )
        try:
            page = int(raw_page)
        except ValueError:
            raise ValueError(f"'{raw_page}' is not a page number.")
        if page < 1:
            raise ValueError("Page numbers start at 1.")

        page_count = int(doc.get("page_count") or 0)
        if page_count and page > page_count:
            raise ValueError(
                f"'{doc['title']}' has {page_count} pages, so page {page} "
                f"does not exist."
            )

        doc_id = doc.get("id")
        return NodeRef(
            document_title=str(doc["title"]),
            file_path=str(doc.get("file_path") or ""),
            page_number=page,
            document_id=int(doc_id) if doc_id is not None else None,
            clause_ref=self.clause_entry.get().strip() or None,
            table_ref=self.table_entry.get().strip() or None,
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _on_save(self) -> None:
        try:
            ref = self._read_reference()
        except ValueError as exc:
            messagebox.showwarning("Eurocode reference", str(exc), parent=self)
            return

        self.node.kind = KIND_CHOICES.get(self.kind_menu.get(), "process")
        self.node.title = self.title_entry.get().strip()[:MAX_TITLE]
        self.node.notes = self.notes_box.get("1.0", "end").strip()[:MAX_NOTES]
        self.node.ref = ref
        self.node.equation = self._equation

        self.saved = True
        self._close()

    def _on_cancel(self) -> None:
        self.saved = False
        self._close()

    def _close(self) -> None:
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()


def edit_node(
    master,
    node: FlowNode,
    documents: List[dict],
    library: Optional[EquationLibrary] = None,
) -> bool:
    """Open the editor modally. Returns True if the node was changed."""
    dialog = NodeEditorDialog(master, node=node, documents=documents,
                              library=library)
    master.wait_window(dialog)
    return dialog.saved
