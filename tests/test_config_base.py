"""Tests for :mod:`spinharmony_studio.config_base`."""

import pytest
from pydantic import BaseModel

from spinharmony_studio.config_base import (
    FortranConfig,
    format_number,
    require_n,
    split_config_lines,
)


class _Dummy(FortranConfig):
    CONFIG_FILENAME = "dummy_config.txt"
    value: float = 1.0

    def _config_lines(self) -> list[str]:
        return [self.keyword("VALUE", self.value), self.keyword("FLAG")]


class _DummyAnyName(FortranConfig):
    value: float = 1.0

    def _config_lines(self) -> list[str]:
        return [self.keyword("VALUE", self.value)]


class _NotImplementedConfig(FortranConfig):
    pass


def test_trims_trailing_zeros():
    assert format_number(8.5) == "8.5"


def test_handles_large_values():
    assert format_number(1234567.891) == "1234567.891"


def test_default_config_lines_raises():
    model = _NotImplementedConfig()
    with pytest.raises(NotImplementedError):
        model._config_lines()


def test_joins_lines_with_trailing_newline():
    text = _Dummy(value=2.5).to_text()
    assert text == "VALUE 2.5\nFLAG\n"


def test_writes_file_and_returns_path(tmp_path):
    target = tmp_path / "dummy_config.txt"
    result = _Dummy(value=3).to_file(target)
    assert result == target
    assert target.read_text() == "VALUE 3\nFLAG\n"


def test_wrong_filename_rejected_when_fixed(tmp_path):
    target = tmp_path / "wrong_name.txt"
    with pytest.raises(ValueError, match="dummy_config.txt"):
        _Dummy().to_file(target)


def test_any_filename_accepted_when_unset(tmp_path):
    target = tmp_path / "whatever.txt"
    result = _DummyAnyName(value=1).to_file(target)
    assert result == target


def test_fmt_num():
    assert FortranConfig.fmt_num(1.0) == "1"


def test_fmt_seq():
    assert FortranConfig.fmt_seq([1.0, 2.5, 3.0]) == "1 2.5 3"


def test_keyword_with_scalar():
    assert FortranConfig.keyword("WEIGHT", 1.5) == "WEIGHT 1.5"


def test_keyword_with_sequence():
    assert FortranConfig.keyword("BOX", (1, 2, 3)) == "BOX 1 2 3"


def test_keyword_with_no_values_is_bare_flag():
    assert FortranConfig.keyword("TEMP_SUBTRACT") == "TEMP_SUBTRACT"


def test_keyword_with_string_value():
    assert FortranConfig.keyword("SCALE", "REFINE") == "SCALE REFINE"


def test_token_rejects_bool():
    with pytest.raises(TypeError):
        FortranConfig.keyword("FLAG", True)


def test_skips_blanks_and_comments():
    text = "\n# comment\nTITLE Foo\n! also a comment\nWEIGHT 1.5\n"
    result = list(split_config_lines(text))
    assert result == [("TITLE", ["Foo"]), ("WEIGHT", ["1.5"])]


def test_uppercases_keyword():
    result = list(split_config_lines("weight 1.0\n"))
    assert result == [("WEIGHT", ["1.0"])]


def test_correct_count_passes():
    require_n(["1", "2", "3"], 3, "BOX")


def test_wrong_count_raises():
    with pytest.raises(ValueError, match="BOX"):
        require_n(["1", "2"], 3, "BOX")


def test_fortran_config_is_a_pydantic_model():
    assert issubclass(FortranConfig, BaseModel)
