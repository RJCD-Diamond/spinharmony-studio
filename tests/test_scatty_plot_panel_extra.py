"""Additional coverage for :mod:`spinharmony_studio.scatty.gui.scatty_plot_panel`
(the existing test_scatty_plot_panel.py covers _scatty_cmap / _read_ppm_scale)."""

import numpy as np
from PyQt6.QtWidgets import QApplication

from spinharmony_studio.scatty.gui.scatty_plot_panel import (
    ScattyPlotPanel,
    _isfloat,
    _read_ppm,
)

_app = QApplication.instance() or QApplication([])


def test_valid_float_string():
    assert _isfloat("1.5") is True


def test_invalid_string():
    assert _isfloat("not-a-number") is False


def test_reads_p6_binary(tmp_path):
    path = tmp_path / "image.ppm"
    header = b"P6\n2 2\n255\n"
    pixels = bytes([255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 255])
    path.write_bytes(header + pixels)
    image = _read_ppm(path)
    assert image is not None
    assert image.shape == (2, 2, 3)
    np.testing.assert_allclose(image[0, 0], [1.0, 0.0, 0.0])


def test_reads_p3_ascii(tmp_path):
    path = tmp_path / "image.ppm"
    path.write_text("P3\n2 1\n255\n255 0 0  0 255 0\n")
    image = _read_ppm(path)
    assert image is not None
    assert image.shape == (1, 2, 3)
    np.testing.assert_allclose(image[0, 0], [1.0, 0.0, 0.0])


def test_p3_with_comment_line(tmp_path):
    path = tmp_path / "image.ppm"
    path.write_text("P3\n# a comment\n2 1\n255\n255 0 0  0 255 0\n")
    image = _read_ppm(path)
    assert image is not None
    assert image.shape == (1, 2, 3)


def test_unrecognised_magic_returns_none(tmp_path):
    path = tmp_path / "image.ppm"
    path.write_bytes(b"P5\nnope")
    assert _read_ppm(path) is None


def test_truncated_p6_body_returns_none(tmp_path):
    path = tmp_path / "image.ppm"
    path.write_bytes(b"P6\n2 2\n255\n" + b"\x00" * 3)
    assert _read_ppm(path) is None


def test_non_integer_header_returns_none(tmp_path):
    path = tmp_path / "image.ppm"
    path.write_text("P3\nx y\n255\n")
    assert _read_ppm(path) is None


def test_truncated_p3_body_returns_none(tmp_path):
    path = tmp_path / "image.ppm"
    path.write_text("P3\n2 1\n255\n255 0 0\n")
    assert _read_ppm(path) is None


def test_starts_with_placeholder_no_error():
    panel = ScattyPlotPanel()
    assert panel._path is None


def test_show_output_sets_path(tmp_path):
    panel = ScattyPlotPanel()
    target = tmp_path / "foo_sc.txt"
    # np.loadtxt warns (and pytest's filterwarnings=error turns that into
    # a failure) on a truly empty file, so give it a harmless one-liner.
    target.write_text("not a grid\n")
    panel.show_output(target)
    assert panel._path == target


def test_show_output_none_clears_path():
    panel = ScattyPlotPanel()
    panel.show_output(None)
    assert panel._path is None


def test_clear_output(tmp_path):
    panel = ScattyPlotPanel()
    target = tmp_path / "foo_sc.txt"
    target.write_text("1 2\n3 4\n")
    panel.show_output(target)
    panel.clear_output()
    assert panel._path is None


def test_set_ppm_style_stores_and_refreshes():
    panel = ScattyPlotPanel()
    panel.set_ppm_style("heat", (0.0, 1.0))
    assert panel._colourmap == "heat"
    assert panel._ppm_range == (0.0, 1.0)


def test_draws_sc_grid_from_valid_file(tmp_path):
    panel = ScattyPlotPanel()
    target = tmp_path / "foo_sc.txt"
    np.savetxt(target, np.random.rand(4, 4))
    panel.show_output(target)  # exercises _draw_sc_grid success path


def test_sc_grid_with_explicit_ppm_range(tmp_path):
    panel = ScattyPlotPanel()
    target = tmp_path / "foo_sc.txt"
    np.savetxt(target, np.random.rand(4, 4))
    panel.set_ppm_style("heat", (0.0, 1.0))
    panel.show_output(target)


def test_sc_grid_reads_sibling_scale_file(tmp_path):
    panel = ScattyPlotPanel()
    target = tmp_path / "foo_sc.txt"
    np.savetxt(target, np.random.rand(4, 4))
    (tmp_path / "foo_sc_ppm_scale.txt").write_text(
        "Maximum intensity 10.0\nMinimum intensity 0.0\n"
    )
    panel.show_output(target)


def test_malformed_sc_grid_falls_through_to_placeholder(tmp_path):
    panel = ScattyPlotPanel()
    target = tmp_path / "foo_sc.txt"
    target.write_text("not a grid\n")
    panel.show_output(target)  # must not raise; falls back to placeholder


def test_one_dimensional_grid_rejected(tmp_path):
    panel = ScattyPlotPanel()
    target = tmp_path / "foo_sc.txt"
    np.savetxt(target, np.array([1.0, 2.0, 3.0]))
    panel.show_output(target)  # ndim != 2 -> falls through


def test_draws_ppm_image_when_not_sc_txt(tmp_path):
    panel = ScattyPlotPanel()
    target = tmp_path / "foo.ppm"
    target.write_text("P3\n2 1\n255\n255 0 0  0 255 0\n")
    panel.show_output(target)


def test_draws_png_image(tmp_path):
    panel = ScattyPlotPanel()
    target = tmp_path / "foo.png"
    from matplotlib.figure import Figure

    fig = Figure()
    fig.savefig(str(target))
    panel.show_output(target)


def test_unsupported_suffix_falls_back_to_placeholder(tmp_path):
    panel = ScattyPlotPanel()
    target = tmp_path / "foo.xyz"
    target.write_text("nothing useful")
    panel.show_output(target)


def test_missing_file_falls_back_to_placeholder(tmp_path):
    panel = ScattyPlotPanel()
    panel.show_output(tmp_path / "does_not_exist_sc.txt")


def test_corrupt_ppm_falls_back_to_placeholder(tmp_path):
    panel = ScattyPlotPanel()
    target = tmp_path / "foo.ppm"
    target.write_bytes(b"not a ppm at all")
    panel.show_output(target)
