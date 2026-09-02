"""Build an equation, see it drawn, and save it to the global library.

The palette exists so an engineer never has to remember LaTeX: every button
inserts the code for the symbol printed on it, at the cursor.

STRICT LIABILITY RULE
---------------------
This dialog writes down a formula and draws it. It does not evaluate it, has
no field for a variable's value, and produces no result. An equation on a
node says "this is the expression that applies here", never "here is the
answer" - the arithmetic, and the responsibility for it, stay with the
engineer.
"""

from __future__ import annotations

from tkinter import messagebox
from typing import Callable, Dict, List, Optional, Tuple

import customtkinter as ctk

from backend.equations import (
    MAX_LATEX,
    MAX_NAME,
    NOT_CALCULATED,
    Equation,
    EquationError,
    EquationLibrary,
)
from backend.indexer import DISCLAIMER

from .equation_render import (
    EquationRenderError, blank_ctk_image, render_ctk_image,
)
from .smooth_scroll import smooth_scroll

MUTED = "#8a8a8a"
ACCENT = "#3b8ed0"
WARNING = "#e0a800"
DANGER = "#c0576b"

PREVIEW_HEIGHT = 54
PREVIEW_DEBOUNCE_MS = 220

# The library picker's empty state - distinct from the node editor's
# "(no equation)", which means one is attached or not.
NO_SAVED_EQUATIONS = "(none saved yet)"

# (button caption, LaTeX inserted, characters to step back into a placeholder)
PALETTE: Dict[str, List[Tuple[str, str, int]]] = {
    "Greek": [
        ("α", r"\alpha ", 0), ("β", r"\beta ", 0),
        ("γ", r"\gamma ", 0), ("δ", r"\delta ", 0),
        ("ε", r"\varepsilon ", 0), ("ζ", r"\zeta ", 0),
        ("η", r"\eta ", 0), ("θ", r"\theta ", 0),
        ("λ", r"\lambda ", 0), ("μ", r"\mu ", 0),
        ("ν", r"\nu ", 0), ("ξ", r"\xi ", 0),
        ("π", r"\pi ", 0), ("ρ", r"\rho ", 0),
        ("σ", r"\sigma ", 0), ("τ", r"\tau ", 0),
        ("φ", r"\phi ", 0), ("χ", r"\chi ", 0),
        ("ψ", r"\psi ", 0), ("ω", r"\omega ", 0),
        ("Γ", r"\Gamma ", 0), ("Δ", r"\Delta ", 0),
        ("Θ", r"\Theta ", 0), ("Λ", r"\Lambda ", 0),
        ("Σ", r"\Sigma ", 0), ("Φ", r"\Phi ", 0),
        ("Ψ", r"\Psi ", 0), ("Ω", r"\Omega ", 0),
    ],
    "Operators": [
        ("+", "+ ", 0), ("−", "- ", 0),
        ("×", r"\times ", 0), ("÷", r"\div ", 0),
        ("·", r"\cdot ", 0), ("±", r"\pm ", 0),
        ("√", r"\sqrt{}", 1), ("xⁿ", "^{}", 1),
        ("xₙ", "_{}", 1), ("a/b", r"\frac{}{}", 3),
        ("∑", r"\sum ", 0), ("∫", r"\int ", 0),
        ("∂", r"\partial ", 0), ("∞", r"\infty ", 0),
        ("( )", r"\left( \right)", 8), ("[ ]", r"\left[ \right]", 8),
        ("| |", r"\left| \right|", 8), ("%", r"\% ", 0),
    ],
    "Relations": [
        ("=", "= ", 0), ("≠", r"\neq ", 0),
        ("≤", r"\leq ", 0), ("≥", r"\geq ", 0),
        ("<", "< ", 0), (">", "> ", 0),
        ("≈", r"\approx ", 0), ("∝", r"\propto ", 0),
        ("→", r"\rightarrow ", 0), ("⇒", r"\Rightarrow ", 0),
    ],
    "Text": [
        ("Rd", "_{Rd}", 0), ("Ed", "_{Ed}", 0),
        ("ck", "_{ck}", 0), ("yk", "_{yk}", 0),
        ("min", r"_{min}", 0), ("max", r"_{max}", 0),
        ("abc", r"\mathrm{}", 1), ("space", r"\; ", 0),
    ],
}

PALETTE_ORDER = ("Greek", "Operators", "Relations", "Text")


class EquationEditorDialog(ctk.CTkToplevel):
    """Compose an equation, preview it, and optionally save it by name.

    ``result`` is the equation the engineer chose to use, or None if they
    cancelled.
    """

    def __init__(
        self,
        master,
        library: EquationLibrary,
        initial: Optional[Equation] = None,
        on_library_changed: Optional[Callable[[], None]] = None,
        standalone: bool = False,
    ) -> None:
        super().__init__(master)

        # Standalone means "opened from the menu to manage the library",
        # rather than "opened from a node to pick an equation for it". The
        # dialog needs no document, no flowchart and no node either way.
        self.standalone = standalone
        self.library = library
        self.result: Optional[Equation] = None
        self.on_library_changed = on_library_changed or (lambda: None)

        self._preview_job: Optional[str] = None
        self._preview_photo = None          # Tk drops uncited images
        self._blank = blank_ctk_image()
        self._last_error: Optional[str] = None

        self.title("Global equation library" if standalone
                   else "Equation editor")
        self.geometry("820x760")
        self.minsize(700, 660)

        self._build_layout()
        self._load_library_list()
        if initial is not None:
            self.name_entry.insert(0, initial.name)
            self.latex_entry.insert(0, initial.latex)
            self.note_entry.insert(0, initial.note)
            self.source_entry.insert(0, initial.source)
        self._schedule_preview()

        self.scroller = smooth_scroll(self._body)

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.bind("<Escape>", lambda _e: self._on_cancel())

        self.transient(master)
        self.after(80, self._focus_first)

    def _focus_first(self) -> None:
        try:
            self.grab_set()
            self.lift()
            self.latex_entry.focus_set()
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
        self._body = body
        row = 0

        # --- the expression ---------------------------------------------
        ctk.CTkLabel(body, text="Equation", anchor="w",
                     font=ctk.CTkFont(size=12, weight="bold")
                     ).grid(row=row, column=0, sticky="ew")
        row += 1

        self.latex_entry = ctk.CTkEntry(
            body, height=40, font=ctk.CTkFont(size=14, family="Consolas"),
            placeholder_text=r"e.g.  v_{Rd,c} = C_{Rd,c} k (100 \rho_l f_{ck})^{1/3}",
        )
        self.latex_entry.grid(row=row, column=0, sticky="ew", pady=(4, 2))
        self.latex_entry.bind("<KeyRelease>", lambda _e: self._schedule_preview())
        row += 1

        ctk.CTkLabel(
            body, anchor="w", justify="left", text_color=MUTED,
            font=ctk.CTkFont(size=11), wraplength=700,
            text="Type it, or build it with the buttons below - they insert "
                 "the code for you at the cursor.",
        ).grid(row=row, column=0, sticky="ew", pady=(0, 10))
        row += 1

        # --- live preview -------------------------------------------------
        preview_frame = ctk.CTkFrame(body)
        preview_frame.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        preview_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            preview_frame, text="Preview", anchor="w", text_color=MUTED,
            font=ctk.CTkFont(size=11),
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(8, 0))

        self.preview_label = ctk.CTkLabel(
            preview_frame, text="", height=PREVIEW_HEIGHT + 16,
            fg_color=("#ffffff", "#2b2f34"), corner_radius=6,
        )
        self.preview_label.grid(row=1, column=0, sticky="ew", padx=12,
                                pady=(4, 6))

        self.preview_error = ctk.CTkLabel(
            preview_frame, text="", anchor="w", justify="left",
            text_color=DANGER, font=ctk.CTkFont(size=11), wraplength=680,
        )
        self.preview_error.grid(row=2, column=0, sticky="ew", padx=12,
                                pady=(0, 10))
        row += 1

        # --- symbol palette -----------------------------------------------
        ctk.CTkLabel(body, text="Symbols", anchor="w",
                     font=ctk.CTkFont(size=12, weight="bold")
                     ).grid(row=row, column=0, sticky="ew")
        row += 1

        palette = ctk.CTkTabview(body, height=190, corner_radius=8)
        palette.grid(row=row, column=0, sticky="ew", pady=(4, 12))
        for group in PALETTE_ORDER:
            palette.add(group)
            self._fill_palette(palette.tab(group), PALETTE[group])
        palette.set(PALETTE_ORDER[0])
        row += 1

        # --- naming and notes ---------------------------------------------
        ctk.CTkLabel(body, text="Name", anchor="w",
                     font=ctk.CTkFont(size=12, weight="bold")
                     ).grid(row=row, column=0, sticky="ew")
        row += 1
        self.name_entry = ctk.CTkEntry(
            body, height=36, font=ctk.CTkFont(size=13),
            placeholder_text="e.g. Punching shear capacity",
        )
        self.name_entry.grid(row=row, column=0, sticky="ew", pady=(4, 10))
        row += 1

        details = ctk.CTkFrame(body, fg_color="transparent")
        details.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        details.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(details, text="Where it is from", text_color=MUTED,
                     anchor="w", font=ctk.CTkFont(size=11)
                     ).grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.source_entry = ctk.CTkEntry(
            details, height=32, placeholder_text="e.g. EN 1992-1-1 Cl 6.4.4",
        )
        self.source_entry.grid(row=0, column=1, sticky="ew")

        ctk.CTkLabel(details, text="Your note", text_color=MUTED, anchor="w",
                     font=ctk.CTkFont(size=11)
                     ).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(6, 0))
        self.note_entry = ctk.CTkEntry(
            details, height=32,
            placeholder_text="optional - what this expression is for",
        )
        self.note_entry.grid(row=1, column=1, sticky="ew", pady=(6, 0))
        row += 1

        # --- the library --------------------------------------------------
        library_frame = ctk.CTkFrame(body)
        library_frame.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        library_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            library_frame, text="Equation library", anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="ew", padx=12, pady=(12, 2))

        ctk.CTkLabel(
            library_frame, anchor="w", justify="left", text_color=MUTED,
            font=ctk.CTkFont(size=11), wraplength=660,
            text="Saved equations are shared by every workflow, so an "
                 "expression only has to be typed once. Build them here "
                 "before you load a single PDF if you like.",
        ).grid(row=1, column=0, columnspan=3, sticky="ew", padx=12, pady=(0, 8))

        self.library_menu = ctk.CTkOptionMenu(
            library_frame, values=[NO_SAVED_EQUATIONS], height=32,
            command=self._on_library_pick,
        )
        self.library_menu.grid(row=2, column=0, columnspan=2, sticky="ew",
                               padx=(12, 8), pady=(0, 12))

        ctk.CTkButton(
            library_frame, text="Delete", width=80, height=32,
            fg_color="transparent", border_width=1, text_color=MUTED,
            command=self._on_delete,
        ).grid(row=2, column=2, sticky="e", padx=(0, 12), pady=(0, 12))
        row += 1

        # --- footer ---------------------------------------------------------
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=1, column=0, sticky="ew", padx=16, pady=(6, 12))
        footer.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            footer, text="  " + NOT_CALCULATED + "  ",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#3d2f00", fg_color=WARNING, corner_radius=6,
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 4))

        ctk.CTkLabel(
            footer, text=DISCLAIMER, anchor="w", text_color=MUTED,
            font=ctk.CTkFont(size=11),
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 10))

        ctk.CTkButton(
            footer, text="Save to library", width=140, height=36,
            fg_color="transparent", border_width=1, text_color=ACCENT,
            command=self._on_save,
        ).grid(row=2, column=0, sticky="w")

        self.cancel_button = ctk.CTkButton(
            footer, text="Cancel", width=90, height=36,
            fg_color="transparent", border_width=1, text_color=MUTED,
            command=self._on_cancel,
        )
        self.cancel_button.grid(row=2, column=2, sticky="e", padx=(0, 8))

        self.use_button = ctk.CTkButton(
            footer, text="Use this equation", width=150, height=36,
            font=ctk.CTkFont(size=13, weight="bold"), command=self._on_use,
        )
        self.use_button.grid(row=2, column=3, sticky="e")

        if self.standalone:
            # Nothing is waiting for an equation, so there is nothing to
            # "use" - the Save button above is the whole point of being here.
            self.cancel_button.grid_remove()
            self.use_button.configure(text="Done", command=self._on_cancel)

    def _fill_palette(self, parent, buttons) -> None:
        columns = 10
        for index in range(columns):
            parent.grid_columnconfigure(index, weight=1)
        for position, (caption, snippet, back) in enumerate(buttons):
            ctk.CTkButton(
                parent, text=caption, width=52, height=30,
                font=ctk.CTkFont(size=13),
                fg_color="transparent", border_width=1, text_color=None,
                command=lambda s=snippet, b=back: self._insert(s, b),
            ).grid(row=position // columns, column=position % columns,
                   padx=2, pady=2, sticky="ew")

    # ------------------------------------------------------------------
    # Editing
    # ------------------------------------------------------------------
    def _insert(self, snippet: str, step_back: int = 0) -> None:
        """Drop a snippet in at the cursor and leave it somewhere useful."""
        entry = self.latex_entry
        current = entry.get()
        if len(current) + len(snippet) > MAX_LATEX:
            self.preview_error.configure(
                text="That equation is as long as this app supports."
            )
            return
        try:
            position = entry.index("insert")
        except Exception:
            position = len(current)
        entry.insert(position, snippet)
        # Land the cursor inside the braces the snippet just added.
        entry.icursor(position + len(snippet) - step_back)
        entry.focus_set()
        self._schedule_preview()

    def _schedule_preview(self) -> None:
        """Redraw shortly after typing stops, not on every keystroke."""
        if self._preview_job is not None:
            try:
                self.after_cancel(self._preview_job)
            except Exception:
                pass
        self._preview_job = self.after(PREVIEW_DEBOUNCE_MS, self._draw_preview)

    def _draw_preview(self) -> None:
        self._preview_job = None
        latex = self.latex_entry.get().strip()
        colour = "#f0f0f0" if ctk.get_appearance_mode() == "Dark" else "#101418"

        if not latex:
            self._clear_preview()
            self.preview_error.configure(text="")
            self._last_error = None
            return

        try:
            photo = render_ctk_image(latex, px_height=PREVIEW_HEIGHT,
                                     color=colour)
        except EquationRenderError as exc:
            self._clear_preview()
            self.preview_error.configure(text=str(exc))
            self._last_error = str(exc)
            return

        self._preview_photo = photo
        self.preview_label.configure(image=photo, text="")
        self.preview_error.configure(text="")
        self._last_error = None

    def _clear_preview(self) -> None:
        """Take the picture off the label, then let it go.

        Order matters: releasing the image first destroys the underlying Tk
        image while the label still refers to it, and reconfiguring the label
        then fails.
        """
        self.preview_label.configure(image=self._blank, text="")
        self._preview_photo = None

    # ------------------------------------------------------------------
    # Library
    # ------------------------------------------------------------------
    def _load_library_list(self, select: Optional[str] = None) -> None:
        names = self.library.names()
        values = names or [NO_SAVED_EQUATIONS]
        self.library_menu.configure(values=values)
        self.library_menu.set(select if select in names else values[0])

    def _on_library_pick(self, name: str) -> None:
        equation = self.library.by_name(name)
        if equation is None:
            return
        self.name_entry.delete(0, "end")
        self.name_entry.insert(0, equation.name)
        self.latex_entry.delete(0, "end")
        self.latex_entry.insert(0, equation.latex)
        self.note_entry.delete(0, "end")
        self.note_entry.insert(0, equation.note)
        self.source_entry.delete(0, "end")
        self.source_entry.insert(0, equation.source)
        self._schedule_preview()

    def _current_equation(self) -> Optional[Equation]:
        """Build an Equation from the fields, complaining if it cannot."""
        latex = self.latex_entry.get().strip()
        name = self.name_entry.get().strip()[:MAX_NAME]

        if not latex:
            messagebox.showwarning(
                "Equation", "Write the equation first.", parent=self)
            return None

        # Refuse to save something that will not draw - a broken expression in
        # the library is worse than no entry at all.
        self._draw_preview()
        if self._last_error:
            messagebox.showwarning(
                "That equation will not draw",
                f"{self._last_error}\n\nFix it before saving.", parent=self)
            return None

        if not name:
            messagebox.showwarning(
                "Equation", "Give the equation a name so you can find it "
                            "again.", parent=self)
            return None

        try:
            return Equation(
                name=name, latex=latex,
                note=self.note_entry.get().strip(),
                source=self.source_entry.get().strip(),
            )
        except EquationError as exc:
            messagebox.showwarning("Equation", str(exc), parent=self)
            return None

    def _on_save(self) -> None:
        equation = self._current_equation()
        if equation is None:
            return

        existing = self.library.by_name(equation.name)
        if existing is not None and existing.latex != equation.latex:
            if not messagebox.askyesno(
                "Replace saved equation",
                f"'{equation.name}' is already in the library with a "
                f"different expression.\n\nReplace it?",
                parent=self,
            ):
                return

        saved = self.library.save_equation(equation)
        try:
            self.library.save_json()
        except OSError as exc:
            messagebox.showerror("Could not save the library", str(exc),
                                 parent=self)
            return

        self._load_library_list(select=saved.name)
        self.on_library_changed()
        self.preview_error.configure(text="")
        messagebox.showinfo(
            "Saved",
            f"'{saved.name}' is in your equation library and available to "
            f"every workflow.",
            parent=self,
        )

    def _on_delete(self) -> None:
        name = self.library_menu.get()
        if self.library.by_name(name) is None:
            return
        if not messagebox.askyesno(
            "Delete equation",
            f"Remove '{name}' from the library?\n\nNodes that already use it "
            f"keep their copy.",
            parent=self,
        ):
            return
        self.library.remove(name)
        try:
            self.library.save_json()
        except OSError as exc:
            messagebox.showerror("Could not save the library", str(exc),
                                 parent=self)
            return
        self._load_library_list()
        self.on_library_changed()

    # ------------------------------------------------------------------
    # Finishing
    # ------------------------------------------------------------------
    def _on_use(self) -> None:
        latex = self.latex_entry.get().strip()
        if not latex:
            messagebox.showwarning(
                "Equation", "Write the equation first.", parent=self)
            return
        self._draw_preview()
        if self._last_error:
            messagebox.showwarning(
                "That equation will not draw",
                f"{self._last_error}\n\nFix it before using it on a node.",
                parent=self)
            return

        name = self.name_entry.get().strip()[:MAX_NAME]
        # An unnamed equation is still usable on a node - it just does not go
        # into the library until it is given a name.
        self.result = Equation(name=name or "Equation", latex=latex,
                               note=self.note_entry.get().strip(),
                               source=self.source_entry.get().strip())
        self._close()

    def _on_cancel(self) -> None:
        self.result = None
        self._close()

    def _close(self) -> None:
        if self._preview_job is not None:
            try:
                self.after_cancel(self._preview_job)
            except Exception:
                pass
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()


def edit_equation(
    master,
    library: EquationLibrary,
    initial: Optional[Equation] = None,
    on_library_changed: Optional[Callable[[], None]] = None,
) -> Optional[Equation]:
    """Open the editor modally. Returns the chosen equation, or None."""
    dialog = EquationEditorDialog(master, library=library, initial=initial,
                                  on_library_changed=on_library_changed)
    master.wait_window(dialog)
    return dialog.result


def manage_equations(
    master,
    library: EquationLibrary,
    on_library_changed: Optional[Callable[[], None]] = None,
) -> None:
    """Open the library on its own, to build equations up front.

    Needs no document, no flowchart and no selected node - an engineer can
    type out their standard expressions before they have loaded anything.
    """
    dialog = EquationEditorDialog(master, library=library,
                                  on_library_changed=on_library_changed,
                                  standalone=True)
    master.wait_window(dialog)
