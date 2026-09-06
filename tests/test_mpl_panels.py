"""Tests for the Qt+matplotlib panel widgets: mpl_panel, plot_panel,
correl_panel."""

import numpy as np
from PyQt6.QtWidgets import QApplication

from spinharmony_studio.spinvert.gui.correl_panel import CorrelPanel
from spinharmony_studio.spinvert.gui.mpl_panel import MplPanel
from spinharmony_studio.spinvert.gui.plot_panel import PlotPanel
from spinharmony_studio.spinvert.gui.plotting import PlotStyle

_app = QApplication.instance() or QApplication([])


def test_constructs_with_default_style():
    panel = MplPanel()
    assert panel.plot_style is not None


def test_constructs_with_custom_style():
    style = PlotStyle(intensity_xlabel="Custom")
    panel = MplPanel(style=style)
    assert panel.plot_style is style


def test_set_plot_style_swaps_and_refreshes():
    panel = MplPanel()
    new_style = PlotStyle(intensity_xlabel="Different")
    panel.set_plot_style(new_style)
    assert panel.plot_style is new_style


def test_save_png_writes_file_and_restores_size(tmp_path):
    panel = MplPanel()
    original_size = panel.figure.get_size_inches()
    out = tmp_path / "plot.png"
    panel.save_png(out)
    assert out.is_file()
    assert out.stat().st_size > 0
    np.testing.assert_allclose(panel.figure.get_size_inches(), original_size)


def test_constructs_with_two_axes():
    panel = PlotPanel()
    assert panel.ax_data is not None
    assert panel.ax_diff is not None


def test_update_data_and_fit_stores_state():
    panel = PlotPanel()
    data = (np.array([1.0]), np.array([2.0]), np.array([0.1]))
    fit = (np.array([1.0]), np.array([2.1]))
    panel.update_data_and_fit(data, fit, "My fit")
    assert panel._data is data
    assert panel._fit is fit
    assert panel._fit_label == "My fit"


def test_plot_panel_update_with_none_does_not_raise():
    panel = PlotPanel()
    panel.update_data_and_fit(None, None)


def test_constructs_with_axes():
    panel = CorrelPanel()
    assert panel.ax is not None


def test_update_scf_stores_state():
    panel = CorrelPanel()
    scf = (np.array([1.0]), np.array([0.5]), np.array([0.01]))
    panel.update_scf(scf, "Label")
    assert panel._scf is scf
    assert panel._label == "Label"


def test_correl_panel_update_with_none_does_not_raise():
    panel = CorrelPanel()
    panel.update_scf(None)
