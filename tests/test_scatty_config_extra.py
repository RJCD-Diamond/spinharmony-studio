"""Additional coverage for :mod:`spinharmony_studio.scatty.config`, filling in
around the existing test_scatty_config.py (which focuses on axis/orthogonality
validation)."""

import pytest

from spinharmony_studio.scatty.config import ScatteringAxis, ScattyConfig

_MINIMAL_TEXT = """\
NAME hk0 plane
X_AXIS 4 0 0 200
Y_AXIS 0 4 0 200
Z_AXIS 0 0 0 0
RADIATION N
"""


def _minimal_kwargs(**overrides):
    kwargs = {
        "NAME": "hk0 plane",
        "X_AXIS": ScatteringAxis(vector=(4.0, 0.0, 0.0), points=200),
        "Y_AXIS": ScatteringAxis(vector=(0.0, 4.0, 0.0), points=200),
        "Z_AXIS": ScatteringAxis(),
        "RADIATION": "N",
    }
    kwargs.update(overrides)
    return kwargs


def test_window_zero_is_valid():
    config = ScattyConfig(**_minimal_kwargs(WINDOW=0))
    assert config.window == 0


def test_window_one_is_invalid():
    with pytest.raises(ValueError, match="WINDOW must be"):
        ScattyConfig(**_minimal_kwargs(WINDOW=1))


def test_window_negative_is_invalid():
    with pytest.raises(ValueError, match="WINDOW must be"):
        ScattyConfig(**_minimal_kwargs(WINDOW=-1))


def test_all_zero_axes_raises():
    with pytest.raises(ValueError, match="must be non-zero"):
        ScattyConfig(
            **_minimal_kwargs(
                X_AXIS=ScatteringAxis(),
                Y_AXIS=ScatteringAxis(),
                Z_AXIS=ScatteringAxis(),
            )
        )


def test_default_range_applied_when_ppm_output_and_unset():
    config = ScattyConfig(**_minimal_kwargs(PPM_OUTPUT=True))
    assert config.ppm_range == (0.0, 1.0)


def test_explicit_range_preserved():
    config = ScattyConfig(**_minimal_kwargs(PPM_OUTPUT=True, PPM_RANGE=(0.2, 0.8)))
    assert config.ppm_range == (0.2, 0.8)


def test_invalid_range_raises():
    with pytest.raises(ValueError, match="min < max"):
        ScattyConfig(**_minimal_kwargs(PPM_RANGE=(1.0, 0.0)))


def test_equal_range_raises():
    with pytest.raises(ValueError, match="min < max"):
        ScattyConfig(**_minimal_kwargs(PPM_RANGE=(0.5, 0.5)))


def test_from_text_minimal():
    config = ScattyConfig.from_text(_MINIMAL_TEXT)
    assert config.name == "hk0 plane"
    assert config.radiation == "N"


def test_expansion_max_error():
    text = _MINIMAL_TEXT + "EXPANSION_MAX_ERROR 0.05\n"
    config = ScattyConfig.from_text(text)
    assert config.expansion_max_error == 0.05


def test_expansion_order():
    text = _MINIMAL_TEXT + "EXPANSION_ORDER 10\n"
    config = ScattyConfig.from_text(text)
    assert config.expansion_order == 10


def test_remove_bragg():
    text = _MINIMAL_TEXT + "REMOVE_BRAGG f\n"
    config = ScattyConfig.from_text(text)
    assert config.remove_bragg == "F"


def test_symmetry_alias_normalised():
    text = _MINIMAL_TEXT + "SYMMETRY m-3m\n"
    config = ScattyConfig.from_text(text)
    assert config.symmetry == "m3m"


def test_symmetry_non_aliased_value_passthrough():
    text = _MINIMAL_TEXT + "SYMMETRY mmm\n"
    config = ScattyConfig.from_text(text)
    assert config.symmetry == "mmm"


def test_bare_flag_present_is_on():
    text = _MINIMAL_TEXT + "MAG_ONLY\n"
    config = ScattyConfig.from_text(text)
    assert config.mag_only is True


def test_bare_flag_explicit_off():
    text = _MINIMAL_TEXT + "MAG_ONLY 0\n"
    config = ScattyConfig.from_text(text)
    assert config.mag_only is False


def test_ppm_range_from_text():
    text = _MINIMAL_TEXT + "PPM_OUTPUT\nPPM_RANGE 0.1 0.9\n"
    config = ScattyConfig.from_text(text)
    assert config.ppm_range == (0.1, 0.9)


def test_ppm_colourmap_from_text():
    text = _MINIMAL_TEXT + "PPM_COLOURMAP HEAT\n"
    config = ScattyConfig.from_text(text)
    assert config.ppm_colourmap == "heat"


def test_centre_from_text():
    text = _MINIMAL_TEXT + "CENTRE 1 2 3\n"
    config = ScattyConfig.from_text(text)
    assert config.centre == (1.0, 2.0, 3.0)


def test_cutoff_and_sum_from_text():
    text = _MINIMAL_TEXT + "CUTOFF 5\nSUM SPHERE\n"
    config = ScattyConfig.from_text(text)
    assert config.cutoff == 5
    assert config.sum_type == "sphere"


def test_unrecognised_keyword_raises():
    with pytest.raises(ValueError, match="Unrecognised keyword"):
        ScattyConfig.from_text(_MINIMAL_TEXT + "NOT_A_KEYWORD 1\n")


def test_centre_wrong_arity_raises():
    with pytest.raises(ValueError, match="CENTRE"):
        ScattyConfig.from_text(_MINIMAL_TEXT + "CENTRE 1 2\n")


def test_axis_wrong_arity_raises():
    with pytest.raises(ValueError, match="X_AXIS"):
        ScattyConfig.from_text("NAME x\nX_AXIS 1 2 3\nRADIATION N\n")


def test_from_file(tmp_path):
    path = tmp_path / "scatty_config.txt"
    path.write_text(_MINIMAL_TEXT)
    config = ScattyConfig.from_file(path)
    assert config.name == "hk0 plane"


def test_round_trips_minimal():
    config = ScattyConfig(**_minimal_kwargs())
    reparsed = ScattyConfig.from_text(config.to_text())
    assert reparsed == config


def test_to_text_includes_optional_fields_when_set():
    config = ScattyConfig(
        **_minimal_kwargs(
            REMOVE_BRAGG="F",
            EXPANSION_MAX_ERROR=0.05,
            EXPANSION_ORDER=10,
            SYMMETRY="mmm",
            MAG_ONLY=True,
            TEMP_SUBTRACT=True,
            SUPERCELL_BRAGG_OUTPUT=True,
        )
    )
    text = config.to_text()
    assert "REMOVE_BRAGG F" in text
    assert "EXPANSION_MAX_ERROR 0.05" in text
    assert "EXPANSION_ORDER 10" in text
    assert "SYMMETRY mmm" in text
    assert "MAG_ONLY" in text
    assert "TEMP_SUBTRACT" in text
    assert "SUPERCELL_BRAGG_OUTPUT" in text


def test_to_text_omits_default_cutoff():
    config = ScattyConfig(**_minimal_kwargs())
    assert "CUTOFF" not in config.to_text()


def test_to_text_includes_nondefault_cutoff():
    config = ScattyConfig(**_minimal_kwargs(CUTOFF=5))
    assert "CUTOFF 5" in config.to_text()


def test_to_text_includes_ppm_range():
    config = ScattyConfig(**_minimal_kwargs(PPM_OUTPUT=True, PPM_RANGE=(0.0, 1.0)))
    assert "PPM_RANGE 0.0 1.0" in config.to_text()


def test_to_text_includes_ppm_colourmap():
    config = ScattyConfig(**_minimal_kwargs(PPM_COLOURMAP="heat"))
    assert "PPM_COLOURMAP heat" in config.to_text()


def test_save_to_file_requires_exact_name(tmp_path):
    config = ScattyConfig(**_minimal_kwargs())
    with pytest.raises(ValueError, match="scatty_config.txt"):
        config.save_to_file(tmp_path / "wrong_name.txt")


def test_save_to_file_writes_file(tmp_path):
    config = ScattyConfig(**_minimal_kwargs())
    target = tmp_path / "scatty_config.txt"
    result = config.save_to_file(target)
    assert result == target
    assert "NAME hk0 plane" in target.read_text()
