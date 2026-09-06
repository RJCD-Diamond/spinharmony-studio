"""Tests for :mod:`spinharmony_studio.spinvert.gui.main_window`."""

import time
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox

import spinharmony_studio.spinvert.gui.main_window as main_window_module
from spinharmony_studio.spinvert.config import (
    CellParameters,
    FormFactorCoefficients,
    SpinvertConfig,
)
from spinharmony_studio.spinvert.gui.main_window import MainWindow

_app = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path_factory):
    """Every test gets its own settings.json location, so this container's
    real, already-populated settings (from prior manual use in this session)
    never leaks into (or gets clobbered by) these tests."""
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


def _make_config(**overrides):
    kwargs = {
        "TITLE": "Foo",
        "CELL": CellParameters(a=5, b=5, c=5, alpha=90, beta=90, gamma=90),
        "SITE": [(0, 0, 0)],
        "SPIN_DIMENSION": 3,
        "FORM_FACTOR_J0": FormFactorCoefficients(A=1, a=1, B=1, b=1, C=1, c=1, D=1),
    }
    kwargs.update(overrides)
    return SpinvertConfig(**kwargs)


class _FakeScattyWindow:
    """A real (small) class rather than a bare MagicMock, since
    _open_scatty_window does isinstance(window, ScattyWindow) - isinstance's
    second argument must be an actual type, not a Mock instance."""

    instances: list = []

    def __init__(self):
        self.show = MagicMock()
        self.raise_ = MagicMock()
        self.activateWindow = MagicMock()
        self.set_working_directory = MagicMock()
        _FakeScattyWindow.instances.append(self)


def _menu_bar_actions(window):
    menu_bar = window.menuBar()
    assert menu_bar is not None
    return menu_bar.actions()


def _submenu_actions(action):
    menu = action.menu()
    assert menu is not None
    return menu.actions()


def test_title_and_defaults():
    window = MainWindow()
    assert window.windowTitle() == "Spinharmony Studio"
    assert window._spinvert_path == ""


def test_restores_persisted_paths():
    with (
        patch.object(
            main_window_module, "load_spinvert_path", lambda: "/fake/spinvert"
        ),
        patch.object(main_window_module, "load_spincorrel_path", lambda: ""),
        patch.object(main_window_module, "load_scatty_path", lambda: ""),
    ):
        window = MainWindow()
    assert window._spinvert_path == "/fake/spinvert"


def test_restores_last_session_workdir(tmp_path):
    (tmp_path / "Foo_data.txt").write_text("")
    with patch.object(
        main_window_module,
        "load_last_session",
        lambda: (str(tmp_path), "Foo"),
    ):
        window = MainWindow()
    assert window.workdir_edit.text() == str(tmp_path)


def test_menu_order():
    window = MainWindow()
    titles = [a.text() for a in _menu_bar_actions(window)]
    assert titles == ["&File", "&Edit", "&Executables", "&View", "&Help"]


def test_file_menu_load_before_save():
    window = MainWindow()
    for action in _menu_bar_actions(window):
        if action.text() == "&File":
            texts = [a.text() for a in _submenu_actions(action)]
            assert texts.index("&Load config") < texts.index("&Save config")


def test_executables_menu_contents():
    window = MainWindow()
    for action in _menu_bar_actions(window):
        if action.text() == "&Executables":
            texts = [a.text() for a in _submenu_actions(action)]
            assert "Set spinvert &executable..." in texts
            assert "&Show configured paths..." in texts


def test_help_menu_contents():
    window = MainWindow()
    for action in _menu_bar_actions(window):
        if action.text() == "&Help":
            texts = [a.text() for a in _submenu_actions(action)]
            assert any("spinvert" in t for t in texts)
            assert any("scatty" in t for t in texts)
            assert any("spinteract" in t for t in texts)
            assert "&About Spinvert Studio" in texts


def test_button_row_load_before_save():
    window = MainWindow()
    assert window.load_button.text() == "Load config"
    assert window.save_button.text() == "Save config"


def test_shows_all_three_paths():
    window = MainWindow()
    window._spinvert_path = "/a/spinvert"
    window._spincorrel_path = ""
    window._scatty_path = "/a/scatty"
    with patch.object(QMessageBox, "information") as mock_info:
        window._show_executable_paths()
    text = mock_info.call_args[0][2]
    assert "/a/spinvert" in text
    assert "spincorrel: not set" in text
    assert "/a/scatty" in text


def test_copy_log_delegates():
    window = MainWindow()
    window.output_log.append("hello")
    window._copy_log()
    clipboard = QApplication.clipboard()
    assert clipboard is not None
    assert clipboard.text() == "hello"


def test_clear_log_empties_view():
    window = MainWindow()
    window.output_log.append("hello")
    window._clear_log()
    assert window.output_log.view.toPlainText() == ""


def test_no_pdf_found_warns():
    window = MainWindow()
    with (
        patch.object(
            main_window_module, "find_program_instructions_pdf", return_value=None
        ),
        patch.object(QMessageBox, "warning") as mock_warn,
    ):
        window._open_program_pdf("spinvert", "spinvert instructions")
    assert mock_warn.called


def test_pdf_found_opens(tmp_path):
    window = MainWindow()
    pdf = tmp_path / "instructions.pdf"
    pdf.write_bytes(b"x")
    with (
        patch.object(
            main_window_module, "find_program_instructions_pdf", return_value=pdf
        ),
        patch.object(
            main_window_module.QDesktopServices, "openUrl", return_value=True
        ) as mock_open,
    ):
        window._open_program_pdf("spinvert", "spinvert instructions")
    assert mock_open.called


def test_open_program_pdf_open_failure_warns(tmp_path):
    window = MainWindow()
    pdf = tmp_path / "instructions.pdf"
    pdf.write_bytes(b"x")
    with (
        patch.object(
            main_window_module, "find_program_instructions_pdf", return_value=pdf
        ),
        patch.object(
            main_window_module.QDesktopServices, "openUrl", return_value=False
        ),
        patch.object(QMessageBox, "warning") as mock_warn,
    ):
        window._open_program_pdf("spinvert", "spinvert instructions")
    assert mock_warn.called


def test_shows_about_dialog():
    window = MainWindow()
    with patch.object(QMessageBox, "about") as mock_about:
        window._show_about()
    assert mock_about.called


def test_set_spinvert_path_persists_and_logs(tmp_path):
    with patch.object(
        main_window_module,
        "save_spinvert_path",
        lambda p: tmp_path / "settings.json",
    ):
        window = MainWindow()
        window._set_spinvert_path("/a/spinvert", persist=True)
    assert window._spinvert_path == "/a/spinvert"
    assert "Saved spinvert executable path" in window.output_log.view.toPlainText()


def test_set_spinvert_path_save_failure_warns():
    def raise_oserror(_p):
        raise OSError("disk full")

    with patch.object(main_window_module, "save_spinvert_path", raise_oserror):
        window = MainWindow()
        with patch.object(QMessageBox, "warning") as mock_warn:
            window._set_spinvert_path("/a/spinvert", persist=True)
    assert mock_warn.called


def test_set_spinvert_path_not_persisted_when_false():
    called = []
    with patch.object(
        main_window_module, "save_spinvert_path", lambda p: called.append(p)
    ):
        window = MainWindow()
        window._set_spinvert_path("/a/spinvert", persist=False)
    assert called == []


def test_set_scatty_path(tmp_path):
    with patch.object(
        main_window_module, "save_scatty_path", lambda p: tmp_path / "settings.json"
    ):
        window = MainWindow()
        window._set_scatty_path("/a/scatty", persist=True)
    assert window._scatty_path == "/a/scatty"


def test_set_spincorrel_path(tmp_path):
    with patch.object(
        main_window_module,
        "save_spincorrel_path",
        lambda p: tmp_path / "settings.json",
    ):
        window = MainWindow()
        window._set_spincorrel_path("/a/spincorrel", persist=True)
    assert window._spincorrel_path == "/a/spincorrel"


def test_browse_executable_sets_path_on_selection(tmp_path):
    window = MainWindow()
    exe = tmp_path / "spinvert"
    exe.write_text("")
    with patch.object(
        main_window_module.QFileDialog,
        "getOpenFileName",
        return_value=(str(exe), ""),
    ):
        with patch.object(window, "_set_spinvert_path") as mock_set:
            window._browse_executable()
    mock_set.assert_called_once_with(str(exe), persist=True)


def test_browse_executable_cancelled_does_nothing():
    window = MainWindow()
    with patch.object(
        main_window_module.QFileDialog, "getOpenFileName", return_value=("", "")
    ):
        with patch.object(window, "_set_spinvert_path") as mock_set:
            window._browse_executable()
    mock_set.assert_not_called()


def test_browse_scatty_falls_back_to_spinvert_dir(tmp_path):
    window = MainWindow()
    window._spinvert_path = str(tmp_path / "spinvert")
    with patch.object(
        main_window_module.QFileDialog,
        "getOpenFileName",
        return_value=("", ""),
    ) as mock_dialog:
        window._browse_scatty()
    assert str(tmp_path) in mock_dialog.call_args.args[2]


def test_browse_spincorrel_falls_back_to_spinvert_dir(tmp_path):
    window = MainWindow()
    window._spinvert_path = str(tmp_path / "spinvert")
    with patch.object(
        main_window_module.QFileDialog,
        "getOpenFileName",
        return_value=("", ""),
    ) as mock_dialog:
        window._browse_spincorrel()
    assert str(tmp_path) in mock_dialog.call_args.args[2]


def test_offers_auto_setup_when_unset():
    window = MainWindow()
    window._spinvert_path = ""
    with patch.object(window, "_offer_auto_setup") as mock_offer:
        window._verify_executable_configured()
    assert mock_offer.called


def test_warns_when_configured_but_missing():
    window = MainWindow()
    window._spinvert_path = "/no/such/executable-xyz"
    with patch.object(QMessageBox, "warning") as mock_warn:
        window._verify_executable_configured()
    assert mock_warn.called


def test_silent_when_configured_and_valid(tmp_path):
    window = MainWindow()
    exe = tmp_path / "spinvert"
    exe.write_text("")
    window._spinvert_path = str(exe)
    with (
        patch.object(main_window_module, "resolve_executable", return_value=str(exe)),
        patch.object(QMessageBox, "warning") as mock_warn,
    ):
        window._verify_executable_configured()
    assert not mock_warn.called


def test_declining_does_nothing():
    window = MainWindow()
    with (
        patch.object(
            QMessageBox, "question", return_value=QMessageBox.StandardButton.No
        ),
        patch.object(window, "_start_auto_setup") as mock_start,
    ):
        window._offer_auto_setup()
    assert not mock_start.called


def test_accepting_without_gfortran_warns():
    window = MainWindow()
    with (
        patch.object(
            QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes
        ),
        patch.object(main_window_module, "gfortran_available", return_value=False),
        patch.object(QMessageBox, "warning") as mock_warn,
        patch.object(window, "_start_auto_setup") as mock_start,
    ):
        window._offer_auto_setup()
    assert mock_warn.called
    assert not mock_start.called


def test_accepting_with_gfortran_starts_setup():
    window = MainWindow()
    with (
        patch.object(
            QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes
        ),
        patch.object(main_window_module, "gfortran_available", return_value=True),
        patch.object(window, "_start_auto_setup") as mock_start,
    ):
        window._offer_auto_setup()
    assert mock_start.called


def test_start_auto_setup_disables_run_actions():
    window = MainWindow()
    with patch.object(main_window_module.SetupWorker, "start"):
        window._start_auto_setup()
    assert window.run_action.isEnabled() is False
    assert window.run_correl_action.isEnabled() is False


def test_start_auto_setup_noop_if_already_running():
    window = MainWindow()
    fake_worker = MagicMock()
    fake_worker.isRunning.return_value = True
    window._setup_worker = fake_worker
    window._start_auto_setup()
    assert window._setup_worker is fake_worker


def test_full_success_flow():
    def fake_setup_spinharmony():
        print("Building...")
        return {"spinvert": "/fake/spinvert", "scatty": "/fake/scatty"}

    window = MainWindow()
    with (
        patch(
            "spinharmony_studio.spinvert.gui.setup_worker.setup_spinharmony",
            fake_setup_spinharmony,
        ),
        patch.object(QMessageBox, "information"),
    ):
        window._start_auto_setup()
        worker = window._setup_worker  # keep alive until fully joined below
        assert worker is not None
        _pump_until(lambda: window._setup_worker is None)
        worker.wait()  # avoid "QThread destroyed while running" on GC
    assert window._spinvert_path == "/fake/spinvert"
    assert window._scatty_path == "/fake/scatty"
    assert window.run_action.isEnabled() is True


def test_full_failure_flow():
    def fake_setup_fail():
        raise RuntimeError("network down")

    window = MainWindow()
    with (
        patch(
            "spinharmony_studio.spinvert.gui.setup_worker.setup_spinharmony",
            fake_setup_fail,
        ),
        patch.object(QMessageBox, "critical"),
    ):
        window._start_auto_setup()
        worker = window._setup_worker
        assert worker is not None
        _pump_until(lambda: window._setup_worker is None)
        worker.wait()
    assert "SpinHarmony setup failed" in window.output_log.view.toPlainText()
    assert window.run_action.isEnabled() is True


def test_creates_and_shows_scatty_window(tmp_path):
    _FakeScattyWindow.instances = []
    window = MainWindow()
    window.workdir_edit.setText(str(tmp_path))
    with patch(
        "spinharmony_studio.scatty.gui.scatty_window.ScattyWindow",
        _FakeScattyWindow,
    ):
        window._open_scatty_window()
    fake = _FakeScattyWindow.instances[0]
    assert window._scatty_window is fake
    fake.show.assert_called_once()
    fake.set_working_directory.assert_called_once()


def test_reuses_existing_scatty_window(tmp_path):
    _FakeScattyWindow.instances = []
    window = MainWindow()
    window.workdir_edit.setText(str(tmp_path))
    with patch(
        "spinharmony_studio.scatty.gui.scatty_window.ScattyWindow",
        _FakeScattyWindow,
    ):
        window._open_scatty_window()
        first = window._scatty_window
        window._open_scatty_window()
    assert window._scatty_window is first
    assert len(_FakeScattyWindow.instances) == 1


def test_browse_workdir_sets_field_and_refreshes(tmp_path):
    (tmp_path / "Foo_data.txt").write_text("")
    window = MainWindow()
    with patch.object(
        main_window_module.QFileDialog,
        "getExistingDirectory",
        return_value=str(tmp_path),
    ):
        window._browse_workdir()
    assert window.workdir_edit.text() == str(tmp_path)
    assert window.title_combo.findText("Foo") >= 0


def test_current_title_strips_whitespace():
    window = MainWindow()
    window.title_combo.setCurrentText("  Foo  ")
    assert window._current_title() == "Foo"


def test_current_workdir_none_for_blank():
    window = MainWindow()
    window.workdir_edit.setText("")
    assert window._current_workdir() is None


def test_current_workdir_none_for_nonexistent():
    window = MainWindow()
    window.workdir_edit.setText("/no/such/dir-xyz")
    assert window._current_workdir() is None


def test_current_workdir_valid(tmp_path):
    window = MainWindow()
    window.workdir_edit.setText(str(tmp_path))
    assert window._current_workdir() == tmp_path


def test_refresh_titles_keeps_remembered_title_without_data_file(tmp_path):
    window = MainWindow()
    window._refresh_titles(str(tmp_path), select="Ghost")
    assert window.title_combo.currentText() == "Ghost"


def test_save_config_no_title_warns(tmp_path):
    window = MainWindow()
    window.workdir_edit.setText(str(tmp_path))
    window.title_combo.setCurrentText("")
    with patch.object(QMessageBox, "warning") as mock_warn:
        result = window._save_config()
    assert result is None
    assert mock_warn.called


def test_save_config_no_workdir_warns():
    window = MainWindow()
    window.title_combo.setCurrentText("Foo")
    window.workdir_edit.setText("")
    with patch.object(QMessageBox, "warning") as mock_warn:
        result = window._save_config()
    assert result is None
    assert mock_warn.called


def test_invalid_config_returns_none(tmp_path):
    window = MainWindow()
    window.workdir_edit.setText(str(tmp_path))
    window.title_combo.setCurrentText("Foo")
    with patch.object(window.config_form, "try_build_config", return_value=None):
        result = window._save_config()
    assert result is None


def test_valid_config_writes_file(tmp_path):
    window = MainWindow()
    window.workdir_edit.setText(str(tmp_path))
    window.title_combo.setCurrentText("Foo")
    result = window._save_config()
    assert result is not None
    assert (tmp_path / "Foo_config.txt").is_file()


def test_no_workdir_uses_browser():
    window = MainWindow()
    window.workdir_edit.setText("")
    with patch.object(window, "_load_config_via_browser") as mock_browser:
        window._load_config()
    assert mock_browser.called


def test_load_config_no_title_warns(tmp_path):
    window = MainWindow()
    window.workdir_edit.setText(str(tmp_path))
    window.title_combo.setCurrentText("")
    with patch.object(QMessageBox, "warning") as mock_warn:
        window._load_config()
    assert mock_warn.called


def test_load_config_missing_file_warns(tmp_path):
    window = MainWindow()
    window.workdir_edit.setText(str(tmp_path))
    window.title_combo.setCurrentText("Foo")
    with patch.object(QMessageBox, "warning") as mock_warn:
        window._load_config()
    assert mock_warn.called


def test_loads_existing_file(tmp_path):
    window = MainWindow()
    window.workdir_edit.setText(str(tmp_path))
    window.title_combo.setCurrentText("Foo")
    _make_config().save_to_file(tmp_path / "Foo_config.txt")
    window._load_config()
    assert "Loaded" in window.output_log.view.toPlainText()


def test_load_config_via_browser_cancelled():
    window = MainWindow()
    with patch.object(
        main_window_module.QFileDialog, "getOpenFileName", return_value=("", "")
    ):
        window._load_config_via_browser()  # must not raise


def test_load_config_via_browser_adopts_workdir(tmp_path):
    window = MainWindow()
    config_path = tmp_path / "Foo_config.txt"
    _make_config().save_to_file(config_path)
    with patch.object(
        main_window_module.QFileDialog,
        "getOpenFileName",
        return_value=(str(config_path), ""),
    ):
        window._load_config_via_browser()
    assert window.workdir_edit.text() == str(tmp_path)
    assert window.title_combo.currentText() == "Foo"


def test_load_config_file_quiet_failure_logs(tmp_path):
    window = MainWindow()
    bad_path = tmp_path / "bad_config.txt"
    bad_path.write_text("not a config")
    window._load_config_file(bad_path, quiet=True)
    assert "Could not auto-load" in window.output_log.view.toPlainText()


def test_load_config_file_loud_failure_shows_dialog(tmp_path):
    window = MainWindow()
    bad_path = tmp_path / "bad_config.txt"
    bad_path.write_text("not a config")
    with patch.object(QMessageBox, "critical") as mock_critical:
        window._load_config_file(bad_path, quiet=False)
    assert mock_critical.called


def test_maybe_autoload_loads_when_present(tmp_path):
    window = MainWindow()
    window.workdir_edit.setText(str(tmp_path))
    _make_config().save_to_file(tmp_path / "Foo_config.txt")
    window.title_combo.blockSignals(True)
    window.title_combo.setCurrentText("Foo")
    window.title_combo.blockSignals(False)
    window._maybe_autoload_config()
    assert "Loaded" in window.output_log.view.toPlainText()


def test_maybe_autoload_noop_without_title():
    window = MainWindow()
    window.title_combo.setCurrentText("")
    window._maybe_autoload_config()  # must not raise


def test_view_config_no_title_or_workdir_warns():
    window = MainWindow()
    with patch.object(QMessageBox, "warning") as mock_warn:
        window._view_config()
    assert mock_warn.called


def test_view_config_missing_file_warns(tmp_path):
    window = MainWindow()
    window.workdir_edit.setText(str(tmp_path))
    window.title_combo.setCurrentText("Foo")
    with patch.object(QMessageBox, "warning") as mock_warn:
        window._view_config()
    assert mock_warn.called


def test_opens_existing_file(tmp_path):
    window = MainWindow()
    window.workdir_edit.setText(str(tmp_path))
    window.title_combo.setCurrentText("Foo")
    (tmp_path / "Foo_config.txt").write_text("TITLE Foo\n")
    with patch.object(
        main_window_module.QDesktopServices, "openUrl", return_value=True
    ) as mock_open:
        window._view_config()
    assert mock_open.called


def test_view_config_open_failure_warns(tmp_path):
    window = MainWindow()
    window.workdir_edit.setText(str(tmp_path))
    window.title_combo.setCurrentText("Foo")
    (tmp_path / "Foo_config.txt").write_text("TITLE Foo\n")
    with (
        patch.object(
            main_window_module.QDesktopServices, "openUrl", return_value=False
        ),
        patch.object(QMessageBox, "warning") as mock_warn,
    ):
        window._view_config()
    assert mock_warn.called


def test_clear_generated_files_no_title_or_workdir_warns():
    window = MainWindow()
    with patch.object(QMessageBox, "warning") as mock_warn:
        window._clear_generated_files()
    assert mock_warn.called


def test_running_guard_warns(tmp_path):
    window = MainWindow()
    window.workdir_edit.setText(str(tmp_path))
    window.title_combo.setCurrentText("Foo")
    window.runner = MagicMock()
    window.runner.is_running.return_value = True
    with patch.object(QMessageBox, "warning") as mock_warn:
        window._clear_generated_files()
    assert mock_warn.called


def test_nothing_to_clear_informs(tmp_path):
    window = MainWindow()
    window.workdir_edit.setText(str(tmp_path))
    window.title_combo.setCurrentText("Foo")
    with patch.object(QMessageBox, "information") as mock_info:
        window._clear_generated_files()
    assert mock_info.called


def test_confirm_no_leaves_files(tmp_path):
    window = MainWindow()
    window.workdir_edit.setText(str(tmp_path))
    window.title_combo.setCurrentText("Foo")
    (tmp_path / "Foo_chi_01.txt").write_text("")
    with patch.object(
        QMessageBox, "question", return_value=QMessageBox.StandardButton.No
    ):
        window._clear_generated_files()
    assert (tmp_path / "Foo_chi_01.txt").is_file()


def test_confirm_yes_deletes_files_and_shows_count_not_names(tmp_path):
    window = MainWindow()
    window.workdir_edit.setText(str(tmp_path))
    window.title_combo.setCurrentText("Foo")
    (tmp_path / "Foo_chi_01.txt").write_text("")
    (tmp_path / "Foo_fit_01.txt").write_text("")
    with patch.object(
        QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes
    ) as mock_question:
        window._clear_generated_files()
    assert not (tmp_path / "Foo_chi_01.txt").exists()
    assert not (tmp_path / "Foo_fit_01.txt").exists()
    dialog_text = mock_question.call_args.args[2]
    assert "Foo_chi_01.txt" not in dialog_text
    assert "2 file(s)" in dialog_text


def test_delegates_to_prepare_executable(tmp_path):
    window = MainWindow()
    exe = tmp_path / "spinvert"
    exe.write_text("")
    with patch.object(
        main_window_module, "prepare_executable", return_value=str(exe)
    ) as mock_prep:
        result = window._prepare_executable(str(exe), "spinvert")
    assert result == str(exe)
    assert mock_prep.called


def test_noop_if_already_running():
    window = MainWindow()
    window.runner = MagicMock()
    window.runner.is_running.return_value = True
    window.correl_runner = MagicMock()
    window.correl_runner.is_running.return_value = False
    with patch.object(window, "_prepare_executable") as mock_prep:
        window._run_spinvert()
    assert not mock_prep.called


def test_no_executable_returns_early():
    window = MainWindow()
    with patch.object(window, "_prepare_executable", return_value=None):
        window._run_spinvert()  # must not raise


def test_run_spinvert_no_workdir_warns(tmp_path):
    window = MainWindow()
    exe = tmp_path / "spinvert"
    exe.write_text("")
    with (
        patch.object(window, "_prepare_executable", return_value=str(exe)),
        patch.object(QMessageBox, "warning") as mock_warn,
    ):
        window._run_spinvert()
    assert mock_warn.called


def test_run_spinvert_no_title_warns(tmp_path):
    window = MainWindow()
    exe = tmp_path / "spinvert"
    exe.write_text("")
    window.workdir_edit.setText(str(tmp_path))
    window.title_combo.setCurrentText("")
    with (
        patch.object(window, "_prepare_executable", return_value=str(exe)),
        patch.object(QMessageBox, "warning") as mock_warn,
    ):
        window._run_spinvert()
    assert mock_warn.called


def test_invalid_config_returns_early(tmp_path):
    window = MainWindow()
    exe = tmp_path / "spinvert"
    exe.write_text("")
    window.workdir_edit.setText(str(tmp_path))
    window.title_combo.setCurrentText("Foo")
    with (
        patch.object(window, "_prepare_executable", return_value=str(exe)),
        patch.object(window.config_form, "try_build_config", return_value=None),
    ):
        window._run_spinvert()  # must not raise; runner never starts
    assert window.runner.is_running() is False


def test_confirm_declined_does_not_start(tmp_path):
    window = MainWindow()
    exe = tmp_path / "spinvert"
    exe.write_text("")
    window.workdir_edit.setText(str(tmp_path))
    window.title_combo.setCurrentText("Foo")
    with (
        patch.object(window, "_prepare_executable", return_value=str(exe)),
        patch.object(main_window_module, "confirm_save_before_run", return_value=False),
    ):
        window._run_spinvert()
    assert window.runner.is_running() is False


def test_successful_start(tmp_path):
    window = MainWindow()
    window.workdir_edit.setText(str(tmp_path))
    window.title_combo.setCurrentText("Foo")
    finished = []
    window.runner.finished.connect(finished.append)
    with (
        patch.object(window, "_prepare_executable", return_value="/bin/echo"),
        patch.object(main_window_module, "confirm_save_before_run", return_value=True),
    ):
        window._run_spinvert()
    _pump_until(lambda: finished)
    assert "Running: /bin/echo" in window.output_log.view.toPlainText()


def test_no_spin_configs_prompts_and_declines(tmp_path):
    window = MainWindow()
    window.workdir_edit.setText(str(tmp_path))
    window.title_combo.setCurrentText("Foo")
    with (
        patch.object(window, "_prepare_executable", return_value="/bin/echo"),
        patch.object(
            QMessageBox, "question", return_value=QMessageBox.StandardButton.No
        ) as mock_question,
    ):
        window._run_spincorrel()
    assert mock_question.called
    assert window.correl_runner.is_running() is False


def test_no_spin_configs_prompt_accepted_runs_anyway(tmp_path):
    window = MainWindow()
    window.workdir_edit.setText(str(tmp_path))
    window.title_combo.setCurrentText("Foo")
    finished = []
    window.correl_runner.finished.connect(finished.append)
    with (
        patch.object(window, "_prepare_executable", return_value="/bin/echo"),
        patch.object(
            QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes
        ),
    ):
        window._run_spincorrel()
    _pump_until(lambda: finished)
    assert window.toggle_correl_action.isChecked() is True


def test_spin_files_present_skips_prompt(tmp_path):
    window = MainWindow()
    window.workdir_edit.setText(str(tmp_path))
    window.title_combo.setCurrentText("Foo")
    (tmp_path / "Foo_spins_01.txt").write_text("")
    finished = []
    window.correl_runner.finished.connect(finished.append)
    with (
        patch.object(window, "_prepare_executable", return_value="/bin/echo"),
        patch.object(QMessageBox, "question") as mock_question,
    ):
        window._run_spincorrel()
    _pump_until(lambda: finished)
    assert not mock_question.called


def test_stops_both_and_logs():
    window = MainWindow()
    window.runner = MagicMock()
    window.runner.is_running.return_value = True
    window.correl_runner = MagicMock()
    window.correl_runner.is_running.return_value = True
    window._stop_running()
    window.runner.stop.assert_called_once()
    window.correl_runner.stop.assert_called_once()


def test_neither_running_logs_message():
    window = MainWindow()
    window.runner = MagicMock()
    window.runner.is_running.return_value = False
    window.correl_runner = MagicMock()
    window.correl_runner.is_running.return_value = False
    window._stop_running()
    assert "No process is running" in window.output_log.view.toPlainText()


def test_success_logs_saved(tmp_path):
    window = MainWindow()
    target = tmp_path / "out.png"
    window._save_panel_png(window.plot_panel, target)
    assert "Saved plot to" in window.output_log.view.toPlainText()
    assert target.is_file()


def test_failure_logs_error(tmp_path):
    window = MainWindow()
    fake_panel = MagicMock()
    fake_panel.save_png.side_effect = RuntimeError("boom")
    window._save_panel_png(fake_panel, tmp_path / "out.png")
    assert "Could not save" in window.output_log.view.toPlainText()


def test_on_run_finished_updates_status_and_snapshots(tmp_path):
    window = MainWindow()
    window.workdir_edit.setText(str(tmp_path))
    window.title_combo.setCurrentText("Foo")
    window._on_run_finished(0)
    assert "exit code 0" in window.status_label.text()
    assert (tmp_path / "Foo_plot.png").is_file()


def test_on_correl_finished_without_scf_skips_snapshot(tmp_path):
    window = MainWindow()
    window.workdir_edit.setText(str(tmp_path))
    window.title_combo.setCurrentText("Foo")
    window._on_correl_finished(0)
    assert not (tmp_path / "Foo_scf.png").exists()


def test_on_correl_finished_with_scf_saves_snapshot(tmp_path):
    window = MainWindow()
    window.workdir_edit.setText(str(tmp_path))
    window.title_combo.setCurrentText("Foo")
    (tmp_path / "Foo_scf.txt").write_text("1.0 0.5 0.01\n")
    window._on_correl_finished(0)
    assert (tmp_path / "Foo_scf.png").is_file()


def test_busy_disables_run_enables_stop():
    window = MainWindow()
    window.runner = MagicMock()
    window.runner.is_running.return_value = True
    window.correl_runner = MagicMock()
    window.correl_runner.is_running.return_value = False
    window._update_run_controls()
    assert window.run_button.isEnabled() is False
    assert window.stop_button.isEnabled() is True


def test_idle_enables_run_disables_stop():
    window = MainWindow()
    window.runner = MagicMock()
    window.runner.is_running.return_value = False
    window.correl_runner = MagicMock()
    window.correl_runner.is_running.return_value = False
    window._update_run_controls()
    assert window.run_button.isEnabled() is True
    assert window.stop_button.isEnabled() is False


def test_poll_files_noop_without_title_or_workdir():
    window = MainWindow()
    window._poll_files()  # must not raise


def test_poll_data_loads_and_redraws(tmp_path):
    window = MainWindow()
    (tmp_path / "Foo_data.txt").write_text("1.0 2.0 0.1\n")
    window._poll_data(tmp_path, "Foo")
    assert window._data is not None


def test_poll_data_skips_unchanged_mtime(tmp_path):
    window = MainWindow()
    path = tmp_path / "Foo_data.txt"
    path.write_text("1.0 2.0 0.1\n")
    window._poll_data(tmp_path, "Foo")
    first_data = window._data
    window._poll_data(tmp_path, "Foo")
    assert window._data is first_data


def test_poll_fit_sets_label_and_data(tmp_path):
    window = MainWindow()
    (tmp_path / "Foo_fit_01.txt").write_text("1.0 2.0\n")
    window._poll_fit(tmp_path, "Foo")
    assert window._fit_label == "Foo_fit_01"


def test_poll_chi_updates_status_label(tmp_path):
    window = MainWindow()
    (tmp_path / "Foo_chi_01.txt").write_text("100 5.5\n200 3.3\n")
    window._poll_chi(tmp_path, "Foo")
    assert "chi^2" in window.status_label.text()


def test_poll_scf_updates_correl_panel(tmp_path):
    window = MainWindow()
    (tmp_path / "Foo_scf.txt").write_text("1.0 0.5 0.01\n")
    window._poll_scf(tmp_path, "Foo")
    assert window._scf is not None


def test_poll_files_calls_all_four(tmp_path):
    window = MainWindow()
    window.workdir_edit.setText(str(tmp_path))
    window.title_combo.setCurrentText("Foo")
    with (
        patch.object(window, "_poll_data") as d,
        patch.object(window, "_poll_fit") as f,
        patch.object(window, "_poll_chi") as c,
        patch.object(window, "_poll_scf") as s,
    ):
        window._poll_files()
    assert d.called and f.called and c.called and s.called


def test_show_event_triggers_verification_once():
    window = MainWindow()
    with patch.object(window, "_verify_executable_configured") as mock_verify:
        window.show()
        window.show()
    assert mock_verify.call_count == 1


def test_close_event_saves_session(tmp_path):
    saved = []
    with patch.object(
        main_window_module,
        "save_last_session",
        lambda workdir, title: saved.append((workdir, title)),
    ):
        window = MainWindow()
        window.workdir_edit.setText(str(tmp_path))
        window.title_combo.setCurrentText("Foo")
        window.close()
    assert saved == [(str(tmp_path), "Foo")]


def test_close_event_ignores_oserror(tmp_path):
    def raise_oserror(_workdir, _title):
        raise OSError("no disk")

    with patch.object(main_window_module, "save_last_session", raise_oserror):
        window = MainWindow()
        window.workdir_edit.setText(str(tmp_path))
        window.close()  # must not raise


def test_constructs_app_and_window():
    # A real QApplication already exists in this test process (module
    # `_app`, and every other test's MainWindow relies on it); Qt only
    # ever allows one per process, so constructing a second real one
    # here (as run_spinharmony's own QApplication(...) call would) is a
    # hard segfault, not a raisable Python error. Replace the class
    # itself with a Mock so that call becomes harmless, while the real
    # MainWindow() construction below it still uses the existing app.
    with (
        patch.object(main_window_module, "QApplication", MagicMock()),
        patch.object(main_window_module.sys, "exit") as mock_exit,
        # showEvent -> _verify_executable_configured would otherwise pop a
        # real, blocking "no executable configured" dialog (no spinvert
        # path is ever set in these isolated-settings tests).
        patch.object(MainWindow, "_verify_executable_configured"),
    ):
        main_window_module.run_spinharmony(["prog"])
    assert mock_exit.called
