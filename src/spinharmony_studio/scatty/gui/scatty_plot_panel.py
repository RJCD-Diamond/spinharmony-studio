"""On-screen panel for whatever output Scatty writes for the current
calculation.

Preferred view: the ``*_sc.txt`` 2-D intensity grid, drawn with imshow using
the same colourmap and intensity range Scatty used for its ``.ppm``, plus a
matplotlib colour bar (so the bar is generated in Python from the colourmap and
the PPM scale rather than read back from ``*_sc_colourbar.ppm``).

Fallback: a rendered ``.ppm`` / ``.png`` image. Scatty output is never shown as
a line plot. Built on the shared :class:`MplPanel`.
"""

from pathlib import Path

import numpy as np
from matplotlib.colors import Colormap, LinearSegmentedColormap

from spinharmony_studio.spinvert.gui.mpl_panel import MplPanel
from spinharmony_studio.spinvert.gui.plotting import PlotStyle

# Scatty's built-in colourmaps (write_ppm in scatty.f90) mapped to matplotlib.
# "default" is Moreland's cool/warm, which matplotlib ships verbatim as
# "coolwarm"; "heat" is a black-red-yellow-white ramp with breakpoints at
# exactly 1/3 and 2/3, rebuilt here so it matches Scatty rather than "hot".
_SCATTY_HEAT = LinearSegmentedColormap.from_list(
    "scatty_heat",
    [(0.0, "#000000"), (1 / 3, "#ff0000"), (2 / 3, "#ffff00"), (1.0, "#ffffff")],
)
_SCATTY_CMAPS: dict[str, str | Colormap] = {
    "default": "coolwarm",
    "heat": _SCATTY_HEAT,
    "jet": "jet",
    "grey1": "gray",
    "grey2": "gray_r",
    "viridis": "viridis",
}


def _scatty_cmap(name: str | None) -> str | Colormap:
    return _SCATTY_CMAPS.get((name or "default").lower(), "coolwarm")


def _read_ppm_scale(path: Path) -> tuple[float, float] | None:
    """Parse ``<stem>_sc_ppm_scale.txt`` (two lines: 'Maximum intensity ...'
    and 'Minimum intensity ...') into ``(vmin, vmax)``."""
    try:
        text = path.read_text()
    except OSError:
        return None
    vmax = vmin = None
    for line in text.splitlines():
        lowered = line.lower()
        tokens = line.replace(":", " ").split()
        nums = [t for t in tokens if _isfloat(t)]
        if not nums:
            continue
        if "maximum" in lowered:
            vmax = float(nums[-1])
        elif "minimum" in lowered:
            vmin = float(nums[-1])
    if vmin is None or vmax is None or vmin >= vmax:
        return None
    return vmin, vmax


def _isfloat(token: str) -> bool:
    try:
        float(token)
    except ValueError:
        return False
    return True


def _read_ppm(path: Path) -> np.ndarray | None:
    """Minimal Netpbm PPM reader (P3 ascii / P6 binary), so a Pillow install is
    not required to preview Scatty's image output."""
    raw = path.read_bytes()
    magic = raw[:2]
    if magic not in (b"P3", b"P6"):
        return None

    idx = 2
    tokens: list[bytes] = []
    while len(tokens) < 3:
        while idx < len(raw) and raw[idx : idx + 1].isspace():
            idx += 1
        if idx < len(raw) and raw[idx : idx + 1] == b"#":
            while idx < len(raw) and raw[idx : idx + 1] not in (b"\n", b"\r"):
                idx += 1
            continue
        start = idx
        while idx < len(raw) and not raw[idx : idx + 1].isspace():
            idx += 1
        tokens.append(raw[start:idx])
    try:
        width, height, maxval = (int(t) for t in tokens)
    except ValueError:
        return None
    idx += 1  # single whitespace separator after maxval

    count = width * height * 3
    if magic == b"P6":
        body = raw[idx : idx + count]
        if len(body) < count:
            return None
        arr = np.frombuffer(body, dtype=np.uint8).reshape(height, width, 3)
    else:
        vals = np.array(raw[idx:].split()[:count], dtype=np.float64)
        if vals.size < count:
            return None
        arr = vals.reshape(height, width, 3)

    arr = arr.astype(np.float64)
    if maxval:
        arr /= maxval
    return np.clip(arr, 0.0, 1.0)


class ScattyPlotPanel(MplPanel):
    def __init__(self, *, style: PlotStyle | None = None, parent=None) -> None:
        super().__init__(style=style, figsize=(5, 5), parent=parent)
        self._path: Path | None = None
        self._colourmap: str | None = None
        self._ppm_range: tuple[float, float] | None = None
        self.ax = self.figure.subplots()
        self.refresh()

    def show_output(self, path: Path | str | None) -> None:
        self._path = Path(path) if path is not None else None
        self.refresh()

    def set_ppm_style(
        self, colourmap: str | None, ppm_range: tuple[float, float] | None
    ) -> None:
        """Tell the panel which Scatty colourmap / intensity range to use when
        drawing ``*_sc.txt`` (from the current config); redraws if needed."""
        self._colourmap = colourmap
        self._ppm_range = ppm_range
        self.refresh()

    def clear_output(self) -> None:
        self.show_output(None)

    def refresh(self) -> None:
        # Rebuild the figure each time: a colour bar adds its own axes, so
        # ax.clear() alone would leak them across redraws.
        self.figure.clear()
        self.ax = self.figure.subplots()
        path = self._path
        drew = False
        if path is not None and path.is_file():
            drew = self._draw_sc_grid(path) or self._draw_image(path)
        if not drew:
            self.ax.text(
                0.5,
                0.5,
                "Run Scatty to see the scattering pattern",
                ha="center",
                va="center",
                transform=self.ax.transAxes,
                color="0.5",
            )
            self.ax.set_xticks([])
            self.ax.set_yticks([])
        self.canvas.draw_idle()

    def _resolve_range(self, path: Path) -> tuple[float | None, float | None]:
        if self._ppm_range is not None:
            return self._ppm_range
        # Sibling written by Scatty next to <stem>_sc.txt / <stem>_sc.ppm.
        scale = path.with_name(path.name.replace("_sc.txt", "_sc_ppm_scale.txt"))
        parsed = _read_ppm_scale(scale) if scale != path else None
        return parsed if parsed is not None else (None, None)

    def _draw_sc_grid(self, path: Path) -> bool:
        if not path.name.endswith("_sc.txt"):
            return False
        try:
            grid = np.loadtxt(path)
        except (OSError, ValueError):
            return False
        if grid.ndim != 2 or min(grid.shape) < 2:
            return False
        vmin, vmax = self._resolve_range(path)
        im = self.ax.imshow(
            grid,
            origin="lower",
            aspect="auto",
            cmap=_scatty_cmap(self._colourmap),
            vmin=vmin,
            vmax=vmax,
        )
        cbar = self.figure.colorbar(im, ax=self.ax)
        cbar.set_label("Intensity")
        self.ax.set_title(path.name)
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        return True

    def _draw_image(self, path: Path) -> bool:
        if path.suffix.lower() not in (".ppm", ".png"):
            return False
        image = None
        if path.suffix.lower() == ".png":
            try:
                import matplotlib.image as mpimg

                image = mpimg.imread(str(path))
            except Exception:
                image = None
        else:
            try:
                image = _read_ppm(path)
            except OSError:
                image = None
        if image is None:
            return False
        self.ax.imshow(image, origin="lower", aspect="equal")
        self.ax.set_title(path.name)
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        return True
