"""Turn a LaTeX string into a picture, using matplotlib's mathtext.

Typesetting only. This module draws the characters the engineer typed and
does nothing else with them - it never parses the maths for meaning, never
substitutes a value, and never computes a result.

matplotlib's own mathtext engine is used rather than a real LaTeX
installation, so the app keeps working offline with nothing else installed.
matplotlib is imported lazily: it costs the best part of a second, and an
engineer who never opens the equation editor should not pay for it.
"""

from __future__ import annotations

import io
import re
from functools import lru_cache
from typing import Optional, Tuple

# Rendered above 1:1 then scaled down, so the result is smooth on screen.
RENDER_DPI = 200
BASE_FONT_PT = 14

MAX_PIXELS = 4_000        # a runaway expression must not eat all the memory


class EquationRenderError(ValueError):
    """The LaTeX could not be typeset."""


_matplotlib_ready = False


def _ensure_matplotlib():
    """Import matplotlib on first use, pinned to the non-interactive backend."""
    global _matplotlib_ready
    from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: F401
    from matplotlib.figure import Figure

    if not _matplotlib_ready:
        import matplotlib
        # Agg only: a GUI backend would try to start its own event loop and
        # fight with Tk.
        matplotlib.use("Agg", force=False)
        _matplotlib_ready = True
    return Figure


def _clean_message(exc: Exception) -> str:
    """Turn a mathtext parse error into something an engineer can act on.

    Raw mathtext errors echo the expression back and can dump the whole
    grammar, which tells a structural engineer nothing. The useful part is
    the sentence after "...Exception:", and even that is worth rewriting for
    the two mistakes people actually make: an unfinished expression and a
    command that does not exist.
    """
    raw = str(exc)

    detail = ""
    for line in raw.split("\n"):
        line = line.strip()
        if "Exception:" in line:
            detail = line.split("Exception:", 1)[1].strip()
            break
    if not detail:
        for line in raw.split("\n"):
            line = line.strip()
            if line and not line.startswith("^"):
                detail = line
                break

    if "found end of text" in detail:
        return ("The expression stops early - something after the last "
                "symbol is missing.")

    unknown = re.search(r"Unknown symbol: (\\[A-Za-z]+)", detail)
    if unknown:
        return f"'{unknown.group(1)}' is not a command the typesetter knows."

    # A grammar dump: keep only what was found and where.
    if len(detail) > 140:
        found = re.search(r"found ([^(]*)\(at char (\d+)\)", detail)
        if found:
            return (f"Unexpected {found.group(1).strip()} at character "
                    f"{found.group(2)}.")
        detail = detail[:137] + "..."

    return detail or "That is not something the maths typesetter understands."


@lru_cache(maxsize=256)
def render_png(
    latex: str,
    font_pt: float = BASE_FONT_PT,
    color: str = "#000000",
    dpi: int = RENDER_DPI,
) -> bytes:
    """Typeset one expression and return it as PNG bytes.

    ``latex`` is the body of the expression, without surrounding ``$``.
    Raises :class:`EquationRenderError` if it will not typeset.
    """
    expression = (latex or "").strip()
    if not expression:
        raise EquationRenderError("There is no equation to draw yet.")

    Figure = _ensure_matplotlib()

    figure = Figure(figsize=(0.01, 0.01), dpi=dpi)
    figure.patch.set_alpha(0.0)
    figure.text(0, 0, f"${expression}$", fontsize=font_pt, color=color)

    buffer = io.BytesIO()
    try:
        figure.savefig(
            buffer, format="png", dpi=dpi, transparent=True,
            bbox_inches="tight", pad_inches=0.06,
        )
    except Exception as exc:                 # mathtext raises many types
        raise EquationRenderError(_clean_message(exc)) from exc
    finally:
        figure.clear()

    return buffer.getvalue()


def render_image(
    latex: str,
    px_height: Optional[int] = None,
    color: str = "#000000",
    font_pt: float = BASE_FONT_PT,
):
    """Typeset an expression and return it as a PIL image.

    ``px_height`` scales the result to that height, keeping the aspect ratio.
    """
    from PIL import Image

    data = render_png(latex, font_pt=font_pt, color=color)
    image = Image.open(io.BytesIO(data))
    image.load()

    if px_height and image.height and image.height != px_height:
        ratio = px_height / image.height
        width = max(1, min(MAX_PIXELS, int(round(image.width * ratio))))
        height = max(1, min(MAX_PIXELS, int(round(px_height))))
        image = image.resize((width, height), Image.LANCZOS)
    return image


def render_photo(
    latex: str,
    px_height: Optional[int] = None,
    color: str = "#000000",
    font_pt: float = BASE_FONT_PT,
):
    """Typeset an expression as a Tk image.

    The caller must keep a reference to what comes back, or Tk will collect
    it and the picture will silently vanish.
    """
    from PIL import ImageTk

    return ImageTk.PhotoImage(
        render_image(latex, px_height=px_height, color=color, font_pt=font_pt)
    )


def render_ctk_image(
    latex: str,
    px_height: int,
    color: str = "#000000",
    font_pt: float = BASE_FONT_PT,
):
    """Typeset an expression as a CustomTkinter image.

    CTkLabel needs a CTkImage rather than a raw Tk one, or the picture is not
    rescaled on a high-DPI display - which is most of them. The full
    resolution render is handed over and CustomTkinter scales it down, so it
    stays sharp however the display is set up.
    """
    import customtkinter as ctk

    image = render_image(latex, color=color, font_pt=font_pt)
    height = max(1, int(px_height))
    ratio = height / image.height if image.height else 1.0
    width = max(1, min(MAX_PIXELS, int(round(image.width * ratio))))
    return ctk.CTkImage(light_image=image, dark_image=image,
                        size=(width, height))


def blank_ctk_image():
    """A 1x1 transparent image, for showing nothing in a CTkLabel.

    CustomTkinter's CTkLabel cannot un-set an image: ``configure(image=None)``
    records the None but its ``_update_image`` only ever *assigns* an image,
    so the underlying widget keeps pointing at the old one. The next
    ``configure`` call then fails with "image ... doesn't exist" once that old
    image has been collected. Assigning a blank image instead is reliable.

    A fresh instance is returned each time rather than a shared one, because a
    CTkImage caches Tk resources belonging to whichever root created them.
    """
    import customtkinter as ctk
    from PIL import Image

    pixel = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    return ctk.CTkImage(light_image=pixel, dark_image=pixel, size=(1, 1))


def measure(latex: str, px_height: int, color: str = "#000000") -> Tuple[int, int]:
    """Width and height the expression would occupy at a given height."""
    image = render_image(latex, px_height=px_height, color=color)
    return image.width, image.height


def is_renderable(latex: str) -> bool:
    """True if the expression typesets. Used to validate before saving."""
    try:
        render_png(latex)
    except EquationRenderError:
        return False
    return True


def describe_problem(latex: str) -> Optional[str]:
    """The reason an expression will not typeset, or None if it is fine."""
    try:
        render_png(latex)
    except EquationRenderError as exc:
        return str(exc)
    return None


def clear_cache() -> None:
    render_png.cache_clear()
