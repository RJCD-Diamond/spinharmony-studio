"""Tests for :mod:`spinharmony_studio.spinvert.config`."""

import pytest
from pydantic import ValidationError

from spinharmony_studio.spinvert.config import (
    CellParameters,
    FormFactorCoefficients,
    SpinvertConfig,
    parse_spinvert_config_text,
)

_MINIMAL_HEISENBERG = """\
TITLE Example
CELL 8.5 8.5 8.5 90 90 90
SITE 0.125 0.125 0.125
SITE 0.875 0.875 0.875
SPIN_DIMENSION 3
FORM_FACTOR_J0 0.422 17.684 0.5948 6.005 0.0043 -0.609 0.0
WEIGHT 0.05
MOVES 5000
BOX 6 6 6
RUNS 10
SCALE REFINE
"""

_ISING_WITH_ANISOTROPY = """\
TITLE Ising
CELL 5 5 5 90 90 90
SITE 0 0 0
ANISOTROPY 0 0 1
SPIN_DIMENSION 1
FORM_FACTOR_J0 0.422 17.684 0.5948 6.005 0.0043 -0.609 0.0
WEIGHT 1
MOVES 300
BOX 5 5 5
"""


def _minimal_kwargs(**overrides):
    kwargs = {
        "TITLE": "Example",
        "CELL": CellParameters(a=8.5, b=8.5, c=8.5, alpha=90, beta=90, gamma=90),
        "SITE": [(0.125, 0.125, 0.125)],
        "SPIN_DIMENSION": 3,
        "FORM_FACTOR_J0": FormFactorCoefficients(
            A=0.422, a=17.684, B=0.5948, b=6.005, C=0.0043, c=-0.609, D=0.0
        ),
    }
    kwargs.update(overrides)
    return kwargs


def test_parses_minimal_heisenberg():
    data = parse_spinvert_config_text(_MINIMAL_HEISENBERG)
    assert data["TITLE"] == "Example"
    assert data["CELL"] == {
        "a": 8.5,
        "b": 8.5,
        "c": 8.5,
        "alpha": 90.0,
        "beta": 90.0,
        "gamma": 90.0,
    }
    assert data["SITE"] == [(0.125, 0.125, 0.125), (0.875, 0.875, 0.875)]
    assert data["SPIN_DIMENSION"] == 3
    assert data["WEIGHT"] == 0.05
    assert data["MOVES"] == 5000
    assert data["BOX"] == (6, 6, 6)
    assert data["RUNS"] == 10
    assert data["SCALE"] == "REFINE"


def test_ignores_blank_lines_and_comments():
    text = "# comment\n\nTITLE Foo\n! also a comment\n"
    data = parse_spinvert_config_text(text)
    assert data["TITLE"] == "Foo"


def test_case_insensitive_keyword():
    data = parse_spinvert_config_text("title lower\n")
    assert data["TITLE"] == "lower"


def test_anisotropy_collected_as_list():
    data = parse_spinvert_config_text(_ISING_WITH_ANISOTROPY)
    assert data["ANISOTROPY"] == [(0.0, 0.0, 1.0)]


def test_temp_subtract_bare_flag_is_true():
    data = parse_spinvert_config_text("TEMP_SUBTRACT\n")
    assert data["TEMP_SUBTRACT"] is True


def test_temp_subtract_explicit_off():
    data = parse_spinvert_config_text("TEMP_SUBTRACT 0\n")
    assert data["TEMP_SUBTRACT"] is False


def test_temp_subtract_explicit_on_value():
    data = parse_spinvert_config_text("TEMP_SUBTRACT yes\n")
    assert data["TEMP_SUBTRACT"] is True


def test_scale_refine_case_insensitive():
    data = parse_spinvert_config_text("SCALE refine\n")
    assert data["SCALE"] == "REFINE"


def test_scale_numeric():
    data = parse_spinvert_config_text("SCALE 12.5\n")
    assert data["SCALE"] == 12.5


def test_form_factor_j2_parsed():
    text = "FORM_FACTOR_J2 1 2 3 4 5 6 7\n"
    data = parse_spinvert_config_text(text)
    assert data["FORM_FACTOR_J2"]["A"] == 1.0
    assert data["FORM_FACTOR_J2"]["D"] == 7.0


def test_c2_and_uiso():
    data = parse_spinvert_config_text("C2 0.5\nUISO 0.01\n")
    assert data["C2"] == 0.5
    assert data["UISO"] == 0.01


def test_unrecognised_keyword_raises():
    with pytest.raises(ValueError, match="Unrecognised keyword"):
        parse_spinvert_config_text("NOT_A_KEYWORD 1\n")


def test_wrong_arity_raises():
    with pytest.raises(ValueError, match="CELL expects 6 values"):
        parse_spinvert_config_text("CELL 1 2 3\n")


def test_site_wrong_arity_raises():
    with pytest.raises(ValueError, match="SITE expects 3 values"):
        parse_spinvert_config_text("SITE 1 2\n")


def test_round_trips_minimal_heisenberg():
    config = SpinvertConfig.from_text(_MINIMAL_HEISENBERG)
    assert config.title == "Example"
    assert config.spin_dimension == 3
    assert config.box == (6, 6, 6)
    assert config.runs == 10


def test_ising_requires_anisotropy():
    config = SpinvertConfig.from_text(_ISING_WITH_ANISOTROPY)
    assert config.anisotropy == [(0.0, 0.0, 1.0)]


def test_from_file(tmp_path):
    path = tmp_path / "Example_config.txt"
    path.write_text(_MINIMAL_HEISENBERG)
    config = SpinvertConfig.from_file(path)
    assert config.title == "Example"


def test_minimal_valid_config_defaults():
    config = SpinvertConfig(**_minimal_kwargs())
    assert config.weight == 1
    assert config.moves == 300
    assert config.box == (5, 5, 5)
    assert config.runs == 1
    assert config.scale == "REFINE"


def test_box_must_be_positive():
    with pytest.raises(ValidationError, match="BOX must contain"):
        SpinvertConfig(**_minimal_kwargs(BOX=(0, 5, 5)))


def test_ising_without_anisotropy_raises():
    with pytest.raises(ValidationError, match="ANISOTROPY is required"):
        SpinvertConfig(**_minimal_kwargs(SPIN_DIMENSION=1))


def test_ising_with_mismatched_anisotropy_count_raises():
    with pytest.raises(ValidationError, match="one vector per SITE"):
        SpinvertConfig(
            **_minimal_kwargs(
                SPIN_DIMENSION=1,
                SITE=[(0, 0, 0), (0.5, 0.5, 0.5)],
                ANISOTROPY=[(0, 0, 1)],
            )
        )


def test_heisenberg_with_anisotropy_raises():
    with pytest.raises(ValidationError, match="should not be given"):
        SpinvertConfig(**_minimal_kwargs(ANISOTROPY=[(0, 0, 1)]))


def test_ising_with_matching_anisotropy_is_valid():
    config = SpinvertConfig(**_minimal_kwargs(SPIN_DIMENSION=1, ANISOTROPY=[(0, 0, 1)]))
    assert config.anisotropy == [(0, 0, 1)]


def test_nonzero_c2_requires_form_factor_j2():
    with pytest.raises(ValidationError, match="FORM_FACTOR_J2 is required"):
        SpinvertConfig(**_minimal_kwargs(C2=0.5))


def test_nonzero_c2_with_j2_is_valid():
    config = SpinvertConfig(
        **_minimal_kwargs(
            C2=0.5,
            FORM_FACTOR_J2=FormFactorCoefficients(A=1, a=2, B=3, b=4, C=5, c=6, D=7),
        )
    )
    assert config.c2 == 0.5


def test_both_backgrounds_set_raises():
    with pytest.raises(ValidationError, match="cannot both be"):
        SpinvertConfig(**_minimal_kwargs(FLAT_BACKGROUND=1.0, LINEAR_BACKGROUND=1.0))


def test_temp_subtract_with_refine_scale_raises():
    with pytest.raises(ValidationError, match="must be a fixed numeric value"):
        SpinvertConfig(**_minimal_kwargs(TEMP_SUBTRACT=True, SCALE="REFINE"))


def test_temp_subtract_with_fixed_scale_is_valid():
    config = SpinvertConfig(**_minimal_kwargs(TEMP_SUBTRACT=True, SCALE=94.4))
    assert config.temp_subtract is True


def test_requires_at_least_one_site():
    with pytest.raises(ValidationError):
        SpinvertConfig(**_minimal_kwargs(SITE=[]))


def test_cell_parameters_must_be_positive():
    with pytest.raises(ValidationError):
        CellParameters(a=-1, b=1, c=1, alpha=90, beta=90, gamma=90)


def test_cell_angle_must_be_less_than_180():
    with pytest.raises(ValidationError):
        CellParameters(a=1, b=1, c=1, alpha=180, beta=90, gamma=90)


def test_to_text_round_trips_minimal():
    config = SpinvertConfig.from_text(_MINIMAL_HEISENBERG)
    text = config.to_text()
    reparsed = SpinvertConfig.from_text(text)
    assert reparsed == config


def test_to_text_omits_default_runs():
    config = SpinvertConfig(**_minimal_kwargs())
    assert "RUNS" not in config.to_text()


def test_to_text_includes_nondefault_runs():
    config = SpinvertConfig(**_minimal_kwargs(RUNS=5))
    assert "RUNS 5" in config.to_text()


def test_to_text_includes_form_factor_j2_when_set():
    config = SpinvertConfig(
        **_minimal_kwargs(
            C2=0.5,
            FORM_FACTOR_J2=FormFactorCoefficients(A=1, a=2, B=3, b=4, C=5, c=6, D=7),
        )
    )
    assert "FORM_FACTOR_J2 1 2 3 4 5 6 7" in config.to_text()


def test_to_text_includes_anisotropy_lines():
    config = SpinvertConfig(**_minimal_kwargs(SPIN_DIMENSION=1, ANISOTROPY=[(0, 0, 1)]))
    assert "ANISOTROPY 0 0 1" in config.to_text()


def test_to_text_includes_flat_background():
    config = SpinvertConfig(**_minimal_kwargs(FLAT_BACKGROUND=1.5))
    assert "FLAT_BACKGROUND 1.5" in config.to_text()


def test_to_text_includes_linear_background():
    config = SpinvertConfig(**_minimal_kwargs(LINEAR_BACKGROUND=2.5))
    assert "LINEAR_BACKGROUND 2.5" in config.to_text()


def test_to_text_includes_c2_and_uiso():
    config = SpinvertConfig(
        **_minimal_kwargs(
            C2=0.5,
            UISO=0.02,
            FORM_FACTOR_J2=FormFactorCoefficients(A=1, a=2, B=3, b=4, C=5, c=6, D=7),
        )
    )
    text = config.to_text()
    assert "C2 0.5" in text
    assert "UISO 0.02" in text


def test_to_text_includes_temp_subtract():
    config = SpinvertConfig(**_minimal_kwargs(TEMP_SUBTRACT=True, SCALE=1.0))
    assert "TEMP_SUBTRACT" in config.to_text()


def test_save_to_file_requires_config_suffix(tmp_path):
    config = SpinvertConfig(**_minimal_kwargs())
    with pytest.raises(ValueError, match="_config.txt"):
        config.save_to_file(tmp_path / "wrong_name.txt")


def test_save_to_file_writes_file(tmp_path):
    config = SpinvertConfig(**_minimal_kwargs())
    target = tmp_path / "Example_config.txt"
    result = config.save_to_file(target)
    assert result == target
    assert target.is_file()
    assert "TITLE Example" in target.read_text()
