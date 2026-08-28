"""Reusable, Qt-free matplotlib drawing helpers for the spinvert GUI.

Each ``draw_*`` function renders one kind of plot onto the matplotlib ``Axes``
it is handed, so the same code backs the on-screen panels, the saved PNG
snapshots and any headless use (tests, notebooks, batch export). Appearance is
controlled entirely by a :class:`PlotStyle`; every field has a sensible default
and can be overridden per instance or with :func:`dataclasses.replace`.
"""

from dataclasses import dataclass, field

import numpy as np
from matplotlib.axes import Axes
from matplotlib.typing import LegendLocType

Vector = np.ndarray
DataTriple = tuple[Vector, Vector, Vector]  # x, y, y-error
FitPair = tuple[Vector, Vector]  # x, y


@dataclass(frozen=True)
class SeriesStyle:
    """Appearance of a single plotted series."""

    color: str = "blue"
    marker: str = ""  # "" -> line only
    linestyle: str = "-"  # "" -> markers only
    marker_size: float = 3.0
    line_width: float = 1.5
    error_color: str = "0.8"
    error_line_width: float = 1.0

    @property
    def fmt(self) -> str:
        return f"{self.marker}{self.linestyle}" or "-"


@dataclass
class PlotStyle:
    """All configurable appearance for the GUI's plots."""

    data: SeriesStyle = field(
        default_factory=lambda: SeriesStyle(
            color="0.4", marker="o", linestyle="", error_color="0.75"
        )
    )
    fit: SeriesStyle = field(default_factory=lambda: SeriesStyle(color="crimson"))
    difference: SeriesStyle = field(default_factory=lambda: SeriesStyle(color="blue"))
    correlation: SeriesStyle = field(
        default_factory=lambda: SeriesStyle(color="blue", marker="o", linestyle="-")
    )

    zero_line: bool = True
    zero_line_color: str = "0.6"
    zero_line_width: float = 1.0
    legend_loc: LegendLocType = "best"

    intensity_xlabel: str = "Q"
    intensity_ylabel: str = "Intensity"
    difference_ylabel: str = "Difference"
    correlation_xlabel: str = "Radial distance (Angstrom)"
    correlation_ylabel: str = "Spin correlation  <S_i . S_j>"

    data_label: str = "Data"
    fit_label: str = "Fit"
    difference_label: str = "Difference"
    correlation_label: str = "SCF"

    # PNG export: a fixed 16:10 canvas, independent of the on-screen size.
    export_size_inches: tuple[float, float] = (10.0, 6.25)
    export_dpi: int = 160


DEFAULT_STYLE = PlotStyle()


def _plot_series(
    ax: Axes,
    x: Vector,
    y: Vector,
    yerr: Vector | None,
    series: SeriesStyle,
    label: str,
) -> None:
    ax.errorbar(
        x,
        y,
        yerr=yerr,
        fmt=series.fmt,
        ms=series.marker_size,
        lw=series.line_width,
        color=series.color,
        ecolor=series.error_color,
        elinewidth=series.error_line_width,
        label=label,
    )


def draw_data_and_fit(
    ax_top: Axes,
    ax_bottom: Axes,
    data: DataTriple | None,
    fit: FitPair | None,
    *,
    style: PlotStyle = DEFAULT_STYLE,
    fit_label: str | None = None,
) -> None:
    """Top axes: data (with error bars) vs. fit. Bottom axes: the difference."""
    ax_top.clear()
    ax_top.set_xlabel(style.intensity_xlabel)
    ax_top.set_ylabel(style.intensity_ylabel)

    drew = False
    if data is not None and data[0].size:
        q, intensity, error = data
        _plot_series(ax_top, q, intensity, error, style.data, style.data_label)
        drew = True
    if fit is not None and fit[0].size:
        ax_top.plot(
            fit[0],
            fit[1],
            style.fit.fmt,
            color=style.fit.color,
            lw=style.fit.line_width,
            label=fit_label or style.fit_label,
        )
        drew = True
    if drew:
        ax_top.legend(loc=style.legend_loc)

    draw_difference(ax_bottom, data, fit, style=style)


def draw_difference(
    ax: Axes,
    data: DataTriple | None,
    fit: FitPair | None,
    *,
    style: PlotStyle = DEFAULT_STYLE,
) -> None:
    """Point-by-point data-minus-fit residual (2nd column of each)."""
    ax.clear()
    ax.set_xlabel(style.intensity_xlabel)
    ax.set_ylabel(style.difference_ylabel)

    if data is None or not data[0].size or fit is None or not fit[0].size:
        return
    q, intensity, error = data
    fit_intensity = fit[1]
    n = min(intensity.size, fit_intensity.size)
    if n == 0:
        return
    q = q[:n]
    residual = intensity[:n] - fit_intensity[:n]
    err = error[:n] if error.size else None

    if style.zero_line:
        ax.axhline(0.0, color=style.zero_line_color, lw=style.zero_line_width)
    _plot_series(ax, q, residual, err, style.difference, style.difference_label)
    ax.legend(loc=style.legend_loc)


def draw_correlation(
    ax: Axes,
    scf: DataTriple | None,
    *,
    style: PlotStyle = DEFAULT_STYLE,
    label: str | None = None,
) -> None:
    """spincorrel spin-correlation function: <S_i.S_j> vs. radial distance."""
    ax.clear()
    ax.set_xlabel(style.correlation_xlabel)
    ax.set_ylabel(style.correlation_ylabel)

    if scf is None or not scf[0].size:
        return
    r, y, sigma = scf
    has_sigma = sigma.size == y.size and bool(np.any(sigma != 0))
    if style.zero_line:
        ax.axhline(0.0, color=style.zero_line_color, lw=style.zero_line_width)
    _plot_series(
        ax,
        r,
        y,
        sigma if has_sigma else None,
        style.correlation,
        label or style.correlation_label,
    )
    ax.legend(loc=style.legend_loc)
