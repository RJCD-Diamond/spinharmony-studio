"""Tests for :mod:`spinharmony_studio.scatty.config`."""

import warnings

import pytest

from spinharmony_studio.scatty.config import (
    ScatteringAxis,
    ScattyConfig,
    ScattyConfigWarning,
)

# The config from the docs' "Quick-start guide": X and Y are not mutually
# orthogonal for this (orthorhombic) crystal, so Scatty's write_fit step
# aborts before writing _sc.txt / _sc.vtk / .ppm.
_NON_ORTHOGONAL_CONFIG = """\
NAME TbODCO3_2K
CENTRE 0 0 0
X_AXIS 6 6 0 55
Y_AXIS -5 0 5 44
Z_AXIS 0 0 0 60
WINDOW 2
CUTOFF 3
PPM_OUTPUT
PPM_RANGE 0.0 1.0
PPM_COLOURMAP heat
SUM parallel
RADIATION N
MAG_ONLY
"""

# Same calculation, but with Y_AXIS along c* so it's orthogonal to X_AXIS,
# and Z_AXIS's stray point count removed.
_CORRECTED_CONFIG = _NON_ORTHOGONAL_CONFIG.replace(
    "Y_AXIS -5 0 5 44", "Y_AXIS 0 0 5 44"
).replace("Z_AXIS 0 0 0 60", "Z_AXIS 0 0 0 0")


class TestScatteringAxisIsZero:
    def test_zero_vector_and_zero_points(self):
        assert ScatteringAxis(vector=(0.0, 0.0, 0.0), points=0).is_zero

    def test_zero_vector_nonzero_points(self):
        # A stray point count on a zero-length axis is still inactive -
        # Scatty collapses it regardless (scatty.f90:144).
        assert ScatteringAxis(vector=(0.0, 0.0, 0.0), points=60).is_zero

    def test_nonzero_vector_zero_points(self):
        assert ScatteringAxis(vector=(1.0, 0.0, 0.0), points=0).is_zero

    def test_nonzero_vector_and_points(self):
        assert not ScatteringAxis(vector=(1.0, 0.0, 0.0), points=55).is_zero


class TestNormaliseAxes:
    def test_zero_vector_nonzero_points_is_collapsed_on_build(self):
        with pytest.warns(ScattyConfigWarning):
            config = ScattyConfig.from_text(_NON_ORTHOGONAL_CONFIG)
        assert config.z_axis == ScatteringAxis()

    def test_collapsed_axis_round_trips_as_fully_zero(self):
        with pytest.warns(ScattyConfigWarning):
            config = ScattyConfig.from_text(_NON_ORTHOGONAL_CONFIG)
        assert "Z_AXIS 0 0 0 0" in config.to_text()
        assert "Z_AXIS 0 0 0 60" not in config.to_text()


class TestCheckAxes:
    def test_non_orthogonal_axes_warn(self):
        with pytest.warns(ScattyConfigWarning, match="orthogonal"):
            ScattyConfig.from_text(_NON_ORTHOGONAL_CONFIG)

    def test_corrected_axes_build_without_warning(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error", ScattyConfigWarning)
            ScattyConfig.from_text(_CORRECTED_CONFIG)


class TestCheckPpmPlane:
    def test_ppm_output_with_only_one_active_axis_warns(self):
        with pytest.warns(ScattyConfigWarning, match="2-D plane"):
            ScattyConfig(
                NAME="line",
                X_AXIS=ScatteringAxis(vector=(1.0, 0.0, 0.0), points=50),
                Y_AXIS=ScatteringAxis(),
                Z_AXIS=ScatteringAxis(),
                RADIATION="N",
                PPM_OUTPUT=True,
            )

    def test_ppm_output_with_a_plane_does_not_warn(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error", ScattyConfigWarning)
            ScattyConfig(
                NAME="plane",
                X_AXIS=ScatteringAxis(vector=(1.0, 0.0, 0.0), points=50),
                Y_AXIS=ScatteringAxis(vector=(0.0, 1.0, 0.0), points=50),
                Z_AXIS=ScatteringAxis(),
                RADIATION="N",
                PPM_OUTPUT=True,
            )
