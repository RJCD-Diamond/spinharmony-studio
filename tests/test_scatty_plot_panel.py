"""Tests for the pure helpers in
:mod:`spinharmony_studio.scatty.gui.scatty_plot_panel` (no Qt needed)."""

from matplotlib.colors import Colormap

from spinharmony_studio.scatty.gui.scatty_plot_panel import (
    _read_ppm_scale,
    _scatty_cmap,
)


class TestScattyCmap:
    def test_known_names_map_to_matplotlib(self):
        assert _scatty_cmap("default") == "coolwarm"
        assert _scatty_cmap("jet") == "jet"
        assert _scatty_cmap("grey1") == "gray"
        assert _scatty_cmap("grey2") == "gray_r"

    def test_heat_is_a_custom_black_red_yellow_white_ramp(self):
        cmap = _scatty_cmap("heat")
        assert isinstance(cmap, Colormap)
        assert cmap(0.0)[:3] == (0.0, 0.0, 0.0)
        assert cmap(1.0)[:3] == (1.0, 1.0, 1.0)
        r, g, b, _ = cmap(1 / 3)  # red corner
        assert r > 0.99 and g < 0.01 and b < 0.01

    def test_none_and_unknown_fall_back_to_default(self):
        assert _scatty_cmap(None) == "coolwarm"
        assert _scatty_cmap("(none)") == "coolwarm"
        assert _scatty_cmap("not-a-map") == "coolwarm"


class TestReadPpmScale:
    def test_parses_scatty_scale_file(self, tmp_path):
        p = tmp_path / "x_sc_ppm_scale.txt"
        p.write_text(
            " Maximum intensity (for scale bar):    1.00000000    \n"
            " Minimum intensity (for scale bar):    0.00000000    \n"
        )
        assert _read_ppm_scale(p) == (0.0, 1.0)

    def test_rejects_degenerate_or_missing(self, tmp_path):
        missing = tmp_path / "nope.txt"
        assert _read_ppm_scale(missing) is None

        flat = tmp_path / "flat_sc_ppm_scale.txt"
        flat.write_text(
            " Maximum intensity (for scale bar):    2.0\n"
            " Minimum intensity (for scale bar):    2.0\n"
        )
        assert _read_ppm_scale(flat) is None
