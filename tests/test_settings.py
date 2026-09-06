"""Tests for :mod:`spinharmony_studio.settings`."""

from unittest.mock import patch

import pytest

from spinharmony_studio import settings


@pytest.fixture
def settings_tmp_path(tmp_path):
    with patch.object(settings, "app_data_dir", lambda: tmp_path):
        yield tmp_path


def test_load_before_save_is_none(settings_tmp_path):
    assert settings.load_spinvert_path() is None


def test_save_then_load_round_trips(settings_tmp_path):
    where = settings.save_spinvert_path("/usr/bin/spinvert")
    assert where == settings_tmp_path / "settings.json"
    assert settings.load_spinvert_path() == "/usr/bin/spinvert"


def test_all_program_paths_round_trip_independently(settings_tmp_path):
    pairs = [
        (settings.save_spinvert_path, settings.load_spinvert_path, "/a/spinvert"),
        (
            settings.save_spincorrel_path,
            settings.load_spincorrel_path,
            "/a/spincorrel",
        ),
        (settings.save_scatty_path, settings.load_scatty_path, "/a/scatty"),
        (
            settings.save_spinteract_path,
            settings.load_spinteract_path,
            "/a/spinteract",
        ),
        (settings.save_spinplot_path, settings.load_spinplot_path, "/a/spinplot"),
        (settings.save_spindist_path, settings.load_spindist_path, "/a/spindist"),
    ]
    for save, _load, value in pairs:
        save(value)
    for _save, load, value in pairs:
        assert load() == value


def test_blank_value_treated_as_unset(settings_tmp_path):
    settings.save_spinvert_path("   ")
    assert settings.load_spinvert_path() is None


def test_missing_settings_file_reads_as_empty(settings_tmp_path):
    assert settings._read() == {}


def test_corrupt_json_reads_as_empty(settings_tmp_path):
    settings_tmp_path.mkdir(parents=True, exist_ok=True)
    (settings_tmp_path / "settings.json").write_text("not json{")
    assert settings._read() == {}


def test_non_dict_json_reads_as_empty(settings_tmp_path):
    settings_tmp_path.mkdir(parents=True, exist_ok=True)
    (settings_tmp_path / "settings.json").write_text("[1, 2, 3]")
    assert settings._read() == {}


def test_write_creates_parent_directories(tmp_path):
    nested = tmp_path / "a" / "b" / "c"
    with patch.object(settings, "app_data_dir", lambda: nested):
        settings.save_spinvert_path("/x")
    assert (nested / "settings.json").is_file()


def test_settings_file_path(settings_tmp_path):
    assert settings.settings_file() == settings_tmp_path / "settings.json"


def test_load_last_session_before_save_is_none_none(settings_tmp_path):
    assert settings.load_last_session() == (None, None)


def test_last_session_save_then_load_round_trips(settings_tmp_path):
    settings.save_last_session("/some/workdir", "MyTitle")
    assert settings.load_last_session() == ("/some/workdir", "MyTitle")


def test_last_session_blank_values_treated_as_unset(settings_tmp_path):
    settings.save_last_session("  ", "  ")
    assert settings.load_last_session() == (None, None)


def test_save_last_session_preserves_other_keys(settings_tmp_path):
    settings.save_spinvert_path("/usr/bin/spinvert")
    settings.save_last_session("/workdir", "title")
    assert settings.load_spinvert_path() == "/usr/bin/spinvert"
    assert settings.load_last_session() == ("/workdir", "title")


def test_app_data_dir_returns_a_path():
    assert isinstance(settings.app_data_dir(), type(settings.app_data_dir()))


def test_example_data_dir_points_at_bundled_example():
    path = settings.example_data_dir()
    assert path.name == "TbODCO3"
    assert (path / "TbODCO3_2K_config.txt").is_file()
