"""Tests for :mod:`spinharmony_studio.spinvert.gui.plotting` (pure matplotlib,
no Qt involved)."""

import numpy as np
from matplotlib.figure import Figure

from spinharmony_studio.spinvert.gui.plotting import (
    DEFAULT_STYLE,
    PlotStyle,
    SeriesStyle,
    draw_correlation,
    draw_data_and_fit,
    draw_difference,
)


def _axes():
    fig = Figure()
    return fig.subplots()


def test_fmt_combines_marker_and_linestyle():
    assert SeriesStyle(marker="o", linestyle="-").fmt == "o-"


def test_fmt_falls_back_to_dash_when_both_empty():
    assert SeriesStyle(marker="", linestyle="").fmt == "-"


def test_none_data_and_fit_does_not_raise():
    draw_data_and_fit(_axes(), _axes(), None, None)


def test_data_only():
    data = (np.array([1.0, 2.0]), np.array([10.0, 20.0]), np.array([1.0, 1.0]))
    draw_data_and_fit(_axes(), _axes(), data, None)


def test_fit_only():
    fit = (np.array([1.0, 2.0]), np.array([9.0, 19.0]))
    draw_data_and_fit(_axes(), _axes(), None, fit)


def test_data_and_fit_draws_legend():
    ax_top = _axes()
    data = (np.array([1.0, 2.0]), np.array([10.0, 20.0]), np.array([1.0, 1.0]))
    fit = (np.array([1.0, 2.0]), np.array([9.0, 19.0]))
    draw_data_and_fit(ax_top, _axes(), data, fit, fit_label="Custom fit")
    assert ax_top.get_legend() is not None


def test_empty_arrays_treated_as_no_data():
    ax_top = _axes()
    empty_data = (np.array([]), np.array([]), np.array([]))
    empty_fit = (np.array([]), np.array([]))
    draw_data_and_fit(ax_top, _axes(), empty_data, empty_fit)
    assert ax_top.get_legend() is None


def test_custom_style_labels_applied():
    ax_top = _axes()
    style = PlotStyle(intensity_xlabel="Custom X", intensity_ylabel="Custom Y")
    draw_data_and_fit(ax_top, _axes(), None, None, style=style)
    assert ax_top.get_xlabel() == "Custom X"
    assert ax_top.get_ylabel() == "Custom Y"


def test_none_data_does_not_raise():
    draw_difference(_axes(), None, None)


def test_missing_fit_does_not_raise():
    data = (np.array([1.0]), np.array([1.0]), np.array([0.1]))
    draw_difference(_axes(), data, None)


def test_computes_residual_with_matching_lengths():
    ax = _axes()
    data = (
        np.array([1.0, 2.0, 3.0]),
        np.array([10.0, 20.0, 30.0]),
        np.array([1.0, 1.0, 1.0]),
    )
    fit = (np.array([1.0, 2.0, 3.0]), np.array([9.0, 18.0, 27.0]))
    draw_difference(ax, data, fit)
    lines = ax.get_lines()
    assert len(lines) >= 1


def test_mismatched_lengths_truncates_to_shorter():
    ax = _axes()
    data = (np.array([1.0, 2.0]), np.array([10.0, 20.0]), np.array([1.0, 1.0]))
    fit = (np.array([1.0]), np.array([9.0]))
    draw_difference(ax, data, fit)  # must not raise on unequal lengths


def test_zero_size_error_array_treated_as_none():
    ax = _axes()
    data = (np.array([1.0]), np.array([10.0]), np.array([]))
    fit = (np.array([1.0]), np.array([9.0]))
    draw_difference(ax, data, fit)


def test_zero_line_disabled():
    ax = _axes()
    data = (np.array([1.0]), np.array([10.0]), np.array([0.1]))
    fit = (np.array([1.0]), np.array([9.0]))
    style = PlotStyle(zero_line=False)
    n_lines_before = len(ax.get_lines())
    draw_difference(ax, data, fit, style=style)
    # Only the residual series line, no axhline.
    assert len(ax.get_lines()) == n_lines_before + 1


def test_none_scf_does_not_raise():
    draw_correlation(_axes(), None)


def test_empty_scf_does_not_raise():
    empty = (np.array([]), np.array([]), np.array([]))
    draw_correlation(_axes(), empty)


def test_draws_with_sigma():
    ax = _axes()
    scf = (np.array([1.0, 2.0]), np.array([0.5, 0.3]), np.array([0.05, 0.02]))
    draw_correlation(ax, scf)
    assert ax.get_legend() is not None


def test_all_zero_sigma_omits_error_bars():
    ax = _axes()
    scf = (np.array([1.0, 2.0]), np.array([0.5, 0.3]), np.array([0.0, 0.0]))
    draw_correlation(ax, scf)  # must not raise


def test_custom_label():
    ax = _axes()
    scf = (np.array([1.0]), np.array([0.5]), np.array([0.0]))
    draw_correlation(ax, scf, label="Custom SCF")
    legend = ax.get_legend()
    assert legend is not None
    legend_texts = [t.get_text() for t in legend.get_texts()]
    assert "Custom SCF" in legend_texts


def test_default_style_is_a_plot_style_instance():
    assert isinstance(DEFAULT_STYLE, PlotStyle)
