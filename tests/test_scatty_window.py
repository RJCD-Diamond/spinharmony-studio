"""Tests for :mod:`spinharmony_studio.scatty.gui.scatty_window`."""

import time
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox

import spinharmony_studio.scatty.gui.scatty_window as scatty_window_module
from spinharmony_studio.scatty.config import ScattyConfig
from spinharmony_studio.scatty.gui.scatty_window import ScattyWindow

_app = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path_factory):
    from spinharmony_studio import settings

    isolated = tmp_path_factory.mktemp("settings")
    with patch.object(settings, "app_data_dir", lambda: isolated):
        yield


def _pump_until(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while not predicate() and time.time() < deadline:
        _app.processEvents()
        time.sleep(0.01)
    assert predicate(), "condition not met before timeout"


def _minimal_config(**overrides):
    kwargs = {
        "NAME": "hkl",
        "X_AXIS": {"vector": (1.0, 0.0, 0.0), "points": 10},
        "Y_AXIS": {"vector": (0.0, 0.0, 0.0), "points": 0},
        "Z_AXIS": {"vector": (0.0, 0.0, 0.0), "points": 0},
        "RADIATION": "N",
    }
    kwargs.update(overrides)
    return ScattyConfig(**kwargs)


def _ready_window(tmp_path, stem="Foo"):
    window = ScattyWindow()
    window.workdir_edit.setText(str(tmp_path))
    window.stem_edit.setText(stem)
    window.config_form.axis_boxes["X_AXIS"][0].setValue(1.0)
    window.config_form.axis_points["X_AXIS"].setValue(10)
    return window


def test_title():
    window = ScattyWindow()
    assert window.windowTitle() == "Scatty configuration"


def test_restores_persisted_path():
    with patch.object(scatty_window_module, "load_scatty_path", lambda: "/fake/scatty"):
        window = ScattyWindow()
    assert window._scatty_path == "/fake/scatty"


def _menu_bar_actions(window):
    menu_bar = window.menuBar()
    assert menu_bar is not None
    return menu_bar.actions()


def _submenu_actions(action):
    menu = action.menu()
    assert menu is not None
    return menu.actions()


def test_menu_order():
    window = ScattyWindow()
    titles = [a.text() for a in _menu_bar_actions(window)]
    assert titles == ["&File", "&Edit", "&Executables", "&View", "&Help"]


def test_file_menu_load_before_save():
    window = ScattyWindow()
    for action in _menu_bar_actions(window):
        if action.text() == "&File":
            texts = [a.text() for a in _submenu_actions(action)]
            assert texts.index("&Load config") < texts.index("&Save config")


def test_help_menu_only_scatty_pdf():
    window = ScattyWindow()
    for action in _menu_bar_actions(window):
        if action.text() == "&Help":
            texts = [a.text() for a in _submenu_actions(action)]
            assert "scatty instructions (PDF)" in texts
            assert "&About Scatty" in texts
            assert not any("spinvert" in t for t in texts)


def test_button_row_load_before_save():
    window = ScattyWindow()
    assert window.load_button.text() == "Load config"
    assert window.save_button.text() == "Save config"


def test_no_pdf_warns():
    window = ScattyWindow()
    with (
        patch.object(
            scatty_window_module,
            "find_program_instructions_pdf",
            return_value=None,
        ),
        patch.object(QMessageBox, "warning") as mock_warn,
    ):
        window._open_program_pdf("scatty", "scatty instructions")
    assert mock_warn.called


def test_pdf_found_opens(tmp_path):
    window = ScattyWindow()
    pdf = tmp_path / "instructions.pdf"
    pdf.write_bytes(b"x")
    with (
        patch.object(
            scatty_window_module, "find_program_instructions_pdf", return_value=pdf
        ),
        patch.object(
            scatty_window_module.QDesktopServices, "openUrl", return_value=True
        ) as mock_open,
    ):
        window._open_program_pdf("scatty", "scatty instructions")
    assert mock_open.called


def test_show_about():
    window = ScattyWindow()
    with patch.object(QMessageBox, "about") as mock_about:
        window._show_about()
    assert mock_about.called


def test_sets_workdir_and_stem(tmp_path):
    window = ScattyWindow()
    window.set_working_directory(str(tmp_path), "MyStem")
    assert window.workdir_edit.text() == str(tmp_path)
    assert window.stem_edit.text() == "MyStem"


def test_autoloads_existing_config(tmp_path):
    _minimal_config().save_to_file(tmp_path / "scatty_config.txt")
    window = ScattyWindow()
    window.set_working_directory(str(tmp_path), "MyStem")
    assert "Loaded" in window.output_log.view.toPlainText()


def test_unchanged_workdir_does_not_reset_stem(tmp_path):
    window = ScattyWindow()
    window.set_working_directory(str(tmp_path), "First")
    window.set_working_directory(str(tmp_path), "Second")
    assert window.stem_edit.text() == "First"


def test_browse_workdir_sets_field(tmp_path):
    window = ScattyWindow()
    with patch.object(
        scatty_window_module.QFileDialog,
        "getExistingDirectory",
        return_value=str(tmp_path),
    ):
        window._browse_workdir()
    assert window.workdir_edit.text() == str(tmp_path)


def test_browse_workdir_cancelled_is_noop():
    window = ScattyWindow()
    with patch.object(
        scatty_window_module.QFileDialog, "getExistingDirectory", return_value=""
    ):
        window._browse_workdir()
    assert window.workdir_edit.text() == ""


def test_current_workdir_none_for_invalid():
    window = ScattyWindow()
    window.workdir_edit.setText("/no/such/dir-xyz")
    assert window._current_workdir() is None


def test_current_workdir_valid(tmp_path):
    window = ScattyWindow()
    window.workdir_edit.setText(str(tmp_path))
    assert window._current_workdir() == tmp_path


def test_config_path(tmp_path):
    window = ScattyWindow()
    assert window._config_path(tmp_path) == tmp_path / "scatty_config.txt"


def test_maybe_autoload_noop_without_workdir():
    window = ScattyWindow()
    window._maybe_autoload_config()  # must not raise


def test_browse_scatty_sets_path(tmp_path):
    window = ScattyWindow()
    exe = tmp_path / "scatty"
    exe.write_text("")
    with patch.object(
        scatty_window_module.QFileDialog,
        "getOpenFileName",
        return_value=(str(exe), ""),
    ):
        with patch.object(window, "_set_scatty_path") as mock_set:
            window._browse_scatty()
    mock_set.assert_called_once_with(str(exe), persist=True)


def test_set_scatty_path_persists_and_logs(tmp_path):
    with patch.object(
        scatty_window_module,
        "save_scatty_path",
        lambda p: tmp_path / "settings.json",
    ):
        window = ScattyWindow()
        window._set_scatty_path("/a/scatty", persist=True)
    assert "Saved scatty executable path" in window.output_log.view.toPlainText()


def test_set_scatty_path_save_failure_warns():
    def raise_oserror(_p):
        raise OSError("disk full")

    with patch.object(scatty_window_module, "save_scatty_path", raise_oserror):
        window = ScattyWindow()
        with patch.object(QMessageBox, "warning") as mock_warn:
            window._set_scatty_path("/a/scatty", persist=True)
    assert mock_warn.called


def test_show_executable_paths():
    window = ScattyWindow()
    window._scatty_path = "/a/scatty"
    with patch.object(QMessageBox, "information") as mock_info:
        window._show_executable_paths()
    assert "/a/scatty" in mock_info.call_args[0][2]


def test_verify_unset_warns():
    window = ScattyWindow()
    window._scatty_path = ""
    with patch.object(QMessageBox, "warning") as mock_warn:
        window._verify_executable_configured()
    assert mock_warn.called


def test_verify_missing_warns():
    window = ScattyWindow()
    window._scatty_path = "/no/such/executable-xyz"
    with patch.object(QMessageBox, "warning") as mock_warn:
        window._verify_executable_configured()
    assert mock_warn.called


def test_verify_valid_is_silent(tmp_path):
    window = ScattyWindow()
    exe = tmp_path / "scatty"
    exe.write_text("")
    window._scatty_path = str(exe)
    with (
        patch.object(scatty_window_module, "resolve_executable", return_value=str(exe)),
        patch.object(QMessageBox, "warning") as mock_warn,
    ):
        window._verify_executable_configured()
    assert not mock_warn.called


def test_save_no_workdir_warns():
    window = ScattyWindow()
    with patch.object(QMessageBox, "warning") as mock_warn:
        result = window._save_config()
    assert result is None
    assert mock_warn.called


def test_save_invalid_config_returns_none(tmp_path):
    window = ScattyWindow()
    window.workdir_edit.setText(str(tmp_path))
    with patch.object(window.config_form, "try_build_config", return_value=None):
        result = window._save_config()
    assert result is None


def test_save_writes_file(tmp_path):
    window = ScattyWindow()
    window.workdir_edit.setText(str(tmp_path))
    window.config_form.axis_boxes["X_AXIS"][0].setValue(1.0)
    window.config_form.axis_points["X_AXIS"].setValue(10)
    result = window._save_config()
    assert result is not None
    assert (tmp_path / "scatty_config.txt").is_file()


def test_load_config_cancelled():
    window = ScattyWindow()
    with patch.object(
        scatty_window_module.QFileDialog, "getOpenFileName", return_value=("", "")
    ):
        window._load_config()  # must not raise


def test_load_config_sets_workdir(tmp_path):
    window = ScattyWindow()
    config_path = tmp_path / "scatty_config.txt"
    _minimal_config().save_to_file(config_path)
    with patch.object(
        scatty_window_module.QFileDialog,
        "getOpenFileName",
        return_value=(str(config_path), ""),
    ):
        window._load_config()
    assert window.workdir_edit.text() == str(tmp_path)
    assert "Loaded" in window.output_log.view.toPlainText()


def test_load_config_file_quiet_failure_logs(tmp_path):
    window = ScattyWindow()
    bad = tmp_path / "bad.txt"
    bad.write_text("garbage")
    window._load_config_file(bad, quiet=True)
    assert "Could not auto-load" in window.output_log.view.toPlainText()


def test_load_config_file_loud_failure_shows_dialog(tmp_path):
    window = ScattyWindow()
    bad = tmp_path / "bad.txt"
    bad.write_text("garbage")
    with patch.object(QMessageBox, "critical") as mock_critical:
        window._load_config_file(bad, quiet=False)
    assert mock_critical.called


def test_view_config_no_workdir_warns():
    window = ScattyWindow()
    with patch.object(QMessageBox, "warning") as mock_warn:
        window._view_config()
    assert mock_warn.called


def test_view_config_missing_file_warns(tmp_path):
    window = ScattyWindow()
    window.workdir_edit.setText(str(tmp_path))
    with patch.object(QMessageBox, "warning") as mock_warn:
        window._view_config()
    assert mock_warn.called


def test_view_config_opens_file(tmp_path):
    window = ScattyWindow()
    window.workdir_edit.setText(str(tmp_path))
    (tmp_path / "scatty_config.txt").write_text("NAME hkl\n")
    with patch.object(
        scatty_window_module.QDesktopServices, "openUrl", return_value=True
    ) as mock_open:
        window._view_config()
    assert mock_open.called


def test_view_config_open_failure_warns(tmp_path):
    window = ScattyWindow()
    window.workdir_edit.setText(str(tmp_path))
    (tmp_path / "scatty_config.txt").write_text("NAME hkl\n")
    with (
        patch.object(
            scatty_window_module.QDesktopServices, "openUrl", return_value=False
        ),
        patch.object(QMessageBox, "warning") as mock_warn,
    ):
        window._view_config()
    assert mock_warn.called


def test_noop_if_already_running(tmp_path):
    window = _ready_window(tmp_path)
    window.runner = MagicMock()
    window.runner.is_running.return_value = True
    with patch.object(scatty_window_module, "prepare_executable") as mock_prep:
        window._run_scatty()
    assert not mock_prep.called


def test_no_executable_returns_early(tmp_path):
    window = _ready_window(tmp_path)
    with patch.object(scatty_window_module, "prepare_executable", return_value=None):
        window._run_scatty()  # must not raise


def test_no_workdir_warns():
    window = ScattyWindow()
    window.stem_edit.setText("Foo")
    with (
        patch.object(
            scatty_window_module, "prepare_executable", return_value="/bin/echo"
        ),
        patch.object(QMessageBox, "warning") as mock_warn,
    ):
        window._run_scatty()
    assert mock_warn.called


def test_no_stem_warns(tmp_path):
    window = ScattyWindow()
    window.workdir_edit.setText(str(tmp_path))
    with (
        patch.object(
            scatty_window_module, "prepare_executable", return_value="/bin/echo"
        ),
        patch.object(QMessageBox, "warning") as mock_warn,
    ):
        window._run_scatty()
    assert mock_warn.called


def test_missing_atoms_spins_prompt_declined(tmp_path):
    window = _ready_window(tmp_path)
    with (
        patch.object(
            scatty_window_module, "prepare_executable", return_value="/bin/echo"
        ),
        patch.object(
            QMessageBox, "question", return_value=QMessageBox.StandardButton.No
        ) as mock_question,
    ):
        window._run_scatty()
    assert mock_question.called
    assert window.runner.is_running() is False


def test_invalid_config_shows_critical(tmp_path):
    window = _ready_window(tmp_path)
    (tmp_path / "Foo_spins_01.txt").write_text("")
    with (
        patch.object(
            scatty_window_module, "prepare_executable", return_value="/bin/echo"
        ),
        patch.object(
            window.config_form,
            "build_config_with_warnings",
            side_effect=ValueError("bad config"),
        ),
        patch.object(QMessageBox, "critical") as mock_critical,
    ):
        window._run_scatty()
    assert mock_critical.called


def test_config_warning_declined_does_not_run(tmp_path):
    window = _ready_window(tmp_path)
    (tmp_path / "Foo_spins_01.txt").write_text("")
    with (
        patch.object(
            scatty_window_module, "prepare_executable", return_value="/bin/echo"
        ),
        patch.object(
            window.config_form,
            "build_config_with_warnings",
            return_value=(_minimal_config(), ["some warning"]),
        ),
        patch.object(
            QMessageBox, "question", return_value=QMessageBox.StandardButton.No
        ),
    ):
        window._run_scatty()
    assert window.runner.is_running() is False


def test_confirm_save_declined_does_not_run(tmp_path):
    window = _ready_window(tmp_path)
    (tmp_path / "Foo_spins_01.txt").write_text("")
    with (
        patch.object(
            scatty_window_module, "prepare_executable", return_value="/bin/echo"
        ),
        patch.object(
            scatty_window_module, "confirm_save_before_run", return_value=False
        ),
    ):
        window._run_scatty()
    assert window.runner.is_running() is False


def test_successful_start(tmp_path):
    window = _ready_window(tmp_path)
    (tmp_path / "Foo_spins_01.txt").write_text("")
    finished = []
    window.runner.finished.connect(finished.append)
    with (
        patch.object(
            scatty_window_module, "prepare_executable", return_value="/bin/echo"
        ),
        patch.object(
            scatty_window_module, "confirm_save_before_run", return_value=True
        ),
    ):
        window._run_scatty()
    _pump_until(lambda: finished)
    assert "Running: /bin/echo" in window.output_log.view.toPlainText()
    assert window.toggle_plot_action.isChecked() is True


def test_stops_running_process(tmp_path):
    window = ScattyWindow()
    window.runner = MagicMock()
    window.runner.is_running.return_value = True
    window._stop()
    window.runner.stop.assert_called_once()


def test_stop_when_idle_logs_message():
    window = ScattyWindow()
    window.runner = MagicMock()
    window.runner.is_running.return_value = False
    window._stop()
    assert "No scatty process is running" in window.output_log.view.toPlainText()


def test_updates_status_label(tmp_path):
    window = ScattyWindow()
    window.workdir_edit.setText(str(tmp_path))
    window._on_finished(0)
    assert "exit code 0" in window.status_label.text()


def test_saves_png_when_output_present(tmp_path):
    window = ScattyWindow()
    window.workdir_edit.setText(str(tmp_path))
    window.stem_edit.setText("Foo")
    (tmp_path / "Foo_hk0_sc.txt").write_text("1 2\n3 4\n")
    window._on_finished(0)
    assert (tmp_path / "Foo_scatty.png").is_file()


def test_png_save_failure_logged(tmp_path):
    window = ScattyWindow()
    window.workdir_edit.setText(str(tmp_path))
    (tmp_path / "Foo_hk0_sc.txt").write_text("1 2\n3 4\n")
    window.stem_edit.setText("Foo")
    with patch.object(window.plot_panel, "save_png", side_effect=RuntimeError("boom")):
        window._on_finished(0)
    assert "Could not save" in window.output_log.view.toPlainText()


def test_running_disables_run_enables_stop():
    window = ScattyWindow()
    window._set_running(True)
    assert window.run_button.isEnabled() is False
    assert window.stop_button.isEnabled() is True


def test_idle_enables_run_disables_stop():
    window = ScattyWindow()
    window._set_running(False)
    assert window.run_button.isEnabled() is True
    assert window.stop_button.isEnabled() is False


def test_none_colourmap_and_range_when_ppm_output_off():
    window = ScattyWindow()
    window.config_form.ppm_output_cb.setChecked(False)
    with patch.object(window.plot_panel, "set_ppm_style") as mock_set:
        window._push_ppm_style()
    mock_set.assert_called_once_with(None, None)


def test_colourmap_and_range_when_ppm_output_on():
    window = ScattyWindow()
    window.config_form.ppm_output_cb.setChecked(True)
    window.config_form.ppm_cmap_combo.setCurrentText("heat")
    window.config_form.ppm_min.setValue(0.1)
    window.config_form.ppm_max.setValue(0.9)
    with patch.object(window.plot_panel, "set_ppm_style") as mock_set:
        window._push_ppm_style()
    mock_set.assert_called_once_with("heat", (0.1, 0.9))


def test_returns_newest_by_mtime(tmp_path):
    old = tmp_path / "old.txt"
    new = tmp_path / "new.txt"
    old.write_text("")
    time.sleep(0.01)
    new.write_text("")
    best, mtime = ScattyWindow._newest([old, new])
    assert best == new


def test_skips_missing_files(tmp_path):
    existing = tmp_path / "exists.txt"
    existing.write_text("")
    best, mtime = ScattyWindow._newest([tmp_path / "missing.txt", existing])
    assert best == existing


def test_empty_list_returns_none():
    best, mtime = ScattyWindow._newest([])
    assert best is None
    assert mtime == -1.0


def test_noop_without_workdir():
    window = ScattyWindow()
    window._poll_output()  # must not raise


def test_finds_stem_matched_sc_txt(tmp_path):
    window = ScattyWindow()
    window.workdir_edit.setText(str(tmp_path))
    window.stem_edit.setText("Foo")
    (tmp_path / "Foo_hk0_sc.txt").write_text("1 2\n3 4\n")
    window._poll_output()
    assert window._last_output == tmp_path / "Foo_hk0_sc.txt"


def test_falls_back_to_any_sc_txt_without_stem_match(tmp_path):
    window = ScattyWindow()
    window.workdir_edit.setText(str(tmp_path))
    window.stem_edit.setText("NoMatch")
    (tmp_path / "Other_hk0_sc.txt").write_text("1 2\n3 4\n")
    window._poll_output()
    assert window._last_output == tmp_path / "Other_hk0_sc.txt"


def test_ignores_colourbar_ppm(tmp_path):
    window = ScattyWindow()
    window.workdir_edit.setText(str(tmp_path))
    (tmp_path / "Foo_hk0_sc_colourbar.ppm").write_text("")
    window._poll_output()
    assert window._last_output is None


def test_skips_unchanged_output_unless_forced(tmp_path):
    window = ScattyWindow()
    window.workdir_edit.setText(str(tmp_path))
    (tmp_path / "Foo_hk0_sc.txt").write_text("1 2\n")
    window._poll_output()
    first = window._last_output
    with patch.object(window.plot_panel, "show_output") as mock_show:
        window._poll_output()
    assert not mock_show.called
    assert window._last_output == first


def test_force_reloads_even_if_unchanged(tmp_path):
    window = ScattyWindow()
    window.workdir_edit.setText(str(tmp_path))
    (tmp_path / "Foo_hk0_sc.txt").write_text("1 2\n")
    window._poll_output()
    with patch.object(window.plot_panel, "show_output") as mock_show:
        window._poll_output(force=True)
    assert mock_show.called


def test_no_output_files_returns_early(tmp_path):
    window = ScattyWindow()
    window.workdir_edit.setText(str(tmp_path))
    window._poll_output()
    assert window._last_output is None


def test_constructs_app_and_window():
    with (
        patch.object(scatty_window_module, "QApplication", MagicMock()),
        patch.object(scatty_window_module.sys, "exit") as mock_exit,
        patch.object(ScattyWindow, "_verify_executable_configured"),
    ):
        scatty_window_module.main(["prog"])
    assert mock_exit.called
