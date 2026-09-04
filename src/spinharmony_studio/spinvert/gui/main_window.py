"""Main window: config editor + spinvert runner + live fit/chi plots."""

import sys
from collections.abc import Sequence
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QAction, QDesktopServices
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from spinharmony_studio.build import gfortran_available
from spinharmony_studio.settings import (
    load_last_session,
    load_scatty_path,
    load_spincorrel_path,
    load_spinvert_path,
    save_last_session,
    save_scatty_path,
    save_spincorrel_path,
    save_spinvert_path,
    settings_file,
)
from spinharmony_studio.spinvert.config import SpinvertConfig
from spinharmony_studio.spinvert.gui.blade_splitter import BladeSplitter
from spinharmony_studio.spinvert.gui.config_form import ConfigFormWidget
from spinharmony_studio.spinvert.gui.config_prompt import confirm_save_before_run
from spinharmony_studio.spinvert.gui.correl_panel import CorrelPanel
from spinharmony_studio.spinvert.gui.data_files import (
    config_file_path,
    data_file_path,
    discover_titles,
    find_latest_numbered_file,
    generated_output_files,
    parse_chi_file,
    parse_data_file,
    parse_fit_file,
    parse_scf_file,
    plot_image_path,
    scf_file_path,
    scf_image_path,
)
from spinharmony_studio.spinvert.gui.executables import (
    prepare_executable,
    resolve_executable,
)
from spinharmony_studio.spinvert.gui.output_log import OutputLog
from spinharmony_studio.spinvert.gui.plot_panel import PlotPanel
from spinharmony_studio.spinvert.gui.setup_worker import SetupWorker
from spinharmony_studio.spinvert.gui.spinvert_runner import SpinvertRunner

# __all__ = ["main"]

POLL_INTERVAL_MS = 1000


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Spinharmony Studio")
        self.resize(1400, 900)

        self.runner = SpinvertRunner(self)
        self.runner.output_received.connect(self._append_log)
        self.runner.finished.connect(self._on_run_finished)

        self.correl_runner = SpinvertRunner(self, program_label="spincorrel")
        self.correl_runner.output_received.connect(self._append_log)
        self.correl_runner.finished.connect(self._on_correl_finished)

        # Paths to the external programs. Chosen from the File menu and
        # remembered between sessions (see settings.py). Never shown in the
        # main layout.
        self._spinvert_path: str = ""
        self._spincorrel_path: str = ""
        self._scatty_path: str = ""
        self._checked_executable = False
        self._scatty_window: QWidget | None = None
        self._setup_worker: SetupWorker | None = None

        self._last_data_mtime: float | None = None
        self._last_fit_path: Path | None = None
        self._last_fit_mtime: float | None = None
        self._last_chi_path: Path | None = None
        self._last_chi_mtime: float | None = None
        self._last_scf_path: Path | None = None
        self._last_scf_mtime: float | None = None
        self._data: tuple | None = None
        self._fit: tuple | None = None
        self._fit_label: str | None = None
        self._scf: tuple | None = None

        central = QWidget()
        self.setCentralWidget(central)
        outer_layout = QVBoxLayout(central)
        outer_layout.addWidget(self._build_program_group())

        self.config_form = ConfigFormWidget()
        self.form_scroll = QScrollArea()
        self.form_scroll.setWidgetResizable(True)
        self.form_scroll.setWidget(self.config_form)

        self.plot_panel = PlotPanel()
        self.correl_panel = CorrelPanel()
        self.output_log = OutputLog()

        # Xbox-360 "blades": left = configuration, centre = fit plot, right =
        # spincorrel plot (starts collapsed). Visible panes share width equally.
        self.blades = BladeSplitter(
            left=self.form_scroll,
            left_label="Configuration",
            center=self.plot_panel,
            right=self.correl_panel,
            right_label="Spin correlation",
            left_visible=True,
            right_visible=False,
        )
        self.blades.left_toggled.connect(
            lambda v: self._sync_toggle(self.toggle_config_action, v)
        )
        self.blades.right_toggled.connect(
            lambda v: self._sync_toggle(self.toggle_correl_action, v)
        )

        # The program-output log spans the full window width below the blades.
        self.body_splitter = QSplitter()
        self.body_splitter.setOrientation(Qt.Orientation.Vertical)
        self.body_splitter.addWidget(self.blades)
        self.body_splitter.addWidget(self.output_log)
        self.body_splitter.setStretchFactor(0, 4)
        self.body_splitter.setStretchFactor(1, 1)
        outer_layout.addWidget(self.body_splitter, stretch=1)
        self._did_initial_split = False

        self._build_menu_bar()

        self.status_label = QLabel("No run in progress.")
        status_bar = self.statusBar()
        assert status_bar is not None
        status_bar.addWidget(self.status_label)
        self.exe_status_label = QLabel()
        status_bar.addPermanentWidget(self.exe_status_label)
        self.correl_status_label = QLabel()
        status_bar.addPermanentWidget(self.correl_status_label)
        self.scatty_status_label = QLabel()
        status_bar.addPermanentWidget(self.scatty_status_label)

        # Restore the external-program paths chosen in a previous session.
        self._set_spinvert_path(load_spinvert_path() or "", persist=False)
        self._set_spincorrel_path(load_spincorrel_path() or "", persist=False)
        self._set_scatty_path(load_scatty_path() or "", persist=False)

        self.timer = QTimer(self)
        self.timer.setInterval(POLL_INTERVAL_MS)
        self.timer.timeout.connect(self._poll_files)
        self.timer.start()

        # Restore the last working directory / title so the previous config
        # reloads (see closeEvent for the matching save).
        last_workdir, last_title = load_last_session()
        if last_workdir and Path(last_workdir).is_dir():
            self.workdir_edit.setText(last_workdir)
            self._refresh_titles(last_workdir, select=last_title)

    # --- layout ----------------------------------------------------------

    def showEvent(self, a0) -> None:  # noqa: N802 (Qt override)
        super().showEvent(a0)
        if not self._did_initial_split:
            self._did_initial_split = True
            height = self.body_splitter.height()
            if height > 0:
                # Blades ~72% / output log ~28% by default; both draggable.
                blades_h = round(height * 0.72)
                self.body_splitter.setSizes([blades_h, height - blades_h])

        if not self._checked_executable:
            self._checked_executable = True
            self._verify_executable_configured()

    def closeEvent(self, a0) -> None:  # noqa: N802 (Qt override)
        # Remember the working directory / title so the last config reloads
        # next launch (restored at the end of __init__).
        workdir = self._current_workdir()
        if workdir is not None:
            try:
                save_last_session(str(workdir), self._current_title())
            except OSError:
                pass
        super().closeEvent(a0)

    @staticmethod
    def _sync_toggle(action: QAction, checked: bool) -> None:
        if action.isChecked() != checked:
            action.blockSignals(True)
            action.setChecked(checked)
            action.blockSignals(False)

    # --- menu bar --------------------------------------------------------

    def _build_menu_bar(self) -> None:
        menu_bar = self.menuBar()
        assert menu_bar is not None

        file_menu = menu_bar.addMenu("&File")
        assert file_menu is not None
        self._add_action(
            file_menu, "Set spinvert &executable...", self._browse_executable
        )
        self._add_action(
            file_menu, "Set spin&correl executable...", self._browse_spincorrel
        )
        self._add_action(file_menu, "Set sca&tty executable...", self._browse_scatty)
        file_menu.addSeparator()
        self._add_action(
            file_menu, "Scatty &configuration window...", self._open_scatty_window
        )
        file_menu.addSeparator()
        self._add_action(file_menu, "&Save config", self._save_config, "Ctrl+S")
        self._add_action(file_menu, "&Load config", self._load_config, "Ctrl+O")
        self._add_action(file_menu, "&View config file", self._view_config)
        self._add_action(
            file_menu, "Clear &generated files", self._clear_generated_files
        )
        file_menu.addSeparator()
        self.run_action = self._add_action(
            file_menu, "&Run spinvert", self._run_spinvert, "Ctrl+R"
        )
        self.run_correl_action = self._add_action(
            file_menu, "Run spi&ncorrel", self._run_spincorrel
        )
        self.stop_action = self._add_action(file_menu, "Sto&p", self._stop_running)
        self.stop_action.setEnabled(False)
        file_menu.addSeparator()
        self._add_action(file_menu, "&Quit", self.close, "Ctrl+Q")

        edit_menu = menu_bar.addMenu("&Edit")
        assert edit_menu is not None
        self._add_action(edit_menu, "&Copy output", self._copy_log, "Ctrl+Shift+C")
        self._add_action(edit_menu, "Clear &output", self._clear_log)

        view_menu = menu_bar.addMenu("&View")
        assert view_menu is not None
        self.toggle_config_action = QAction("Show &configuration panel", self)
        self.toggle_config_action.setCheckable(True)
        self.toggle_config_action.setChecked(True)
        self.toggle_config_action.setShortcut("F9")
        self.toggle_config_action.toggled.connect(self.blades.set_left_visible)
        view_menu.addAction(self.toggle_config_action)

        self.toggle_correl_action = QAction("Show spin&correl panel", self)
        self.toggle_correl_action.setCheckable(True)
        self.toggle_correl_action.setChecked(False)
        self.toggle_correl_action.setShortcut("F10")
        self.toggle_correl_action.toggled.connect(self.blades.set_right_visible)
        view_menu.addAction(self.toggle_correl_action)

        help_menu = menu_bar.addMenu("&Help")
        assert help_menu is not None
        self._add_action(help_menu, "&About Spinvert Studio", self._show_about)

    def _add_action(self, menu, text, slot, shortcut: str | None = None) -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(shortcut)
        action.triggered.connect(lambda: slot())
        menu.addAction(action)
        return action

    def _copy_log(self) -> None:
        self.output_log.copy_all()

    def _clear_log(self) -> None:
        self.output_log.clear()

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About Spinvert Studio",
            "Spinvert Studio\n\n"
            "Spinvert is a program for refinement of atomistic models to powder "
            "magnetic diffuse scattering data for frustrated magnets, spin glasses, "
            "and other magnetically disordered materials. "
            "For issues/feature requests with the user interface contact: "
            "Richard Dixey at richard.dixey@diamond.ac.uk "
            "Or add submit a request on github "
            "\n\n"
            "For issues/feature requests with of the underlying SPINVERT program "
            "Contact Joe Paddison",
        )

    # --- top control bar --------------------------------------------------

    def _build_program_group(self) -> QGroupBox:
        group = QGroupBox("Working directory")
        layout = QVBoxLayout(group)

        dir_row = QHBoxLayout()
        self.workdir_edit = QLineEdit()
        self.workdir_edit.setPlaceholderText(
            "Working directory containing [title]_data.txt"
        )
        dir_browse = QPushButton("Browse...")
        dir_browse.clicked.connect(self._browse_workdir)
        dir_row.addWidget(QLabel("Working directory"))
        dir_row.addWidget(self.workdir_edit, stretch=1)
        dir_row.addWidget(dir_browse)
        layout.addLayout(dir_row)

        title_row = QHBoxLayout()
        self.title_combo = QComboBox()
        self.title_combo.setEditable(True)
        self.title_combo.currentTextChanged.connect(self._on_title_changed)
        title_row.addWidget(QLabel("Title"))
        title_row.addWidget(self.title_combo, stretch=1)
        layout.addLayout(title_row)

        button_row = QHBoxLayout()
        self.save_button = QPushButton("Save config")
        self.load_button = QPushButton("Load config")
        self.view_config_button = QPushButton("View config file")
        self.clear_files_button = QPushButton("Clear generated files")
        self.run_button = QPushButton("Run spinvert")
        self.run_correl_button = QPushButton("Run spincorrel")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.scatty_button = QPushButton("Scatty configuration...")
        self.scatty_button.setToolTip(
            "Open the Scatty configuration window (uses this working directory)"
        )
        self.save_button.clicked.connect(self._save_config)
        self.load_button.clicked.connect(self._load_config)
        self.view_config_button.clicked.connect(self._view_config)
        self.clear_files_button.clicked.connect(self._clear_generated_files)
        self.run_button.clicked.connect(self._run_spinvert)
        self.run_correl_button.clicked.connect(self._run_spincorrel)
        self.stop_button.clicked.connect(self._stop_running)
        self.scatty_button.clicked.connect(self._open_scatty_window)
        button_row.addWidget(self.save_button)
        button_row.addWidget(self.load_button)
        button_row.addWidget(self.view_config_button)
        button_row.addWidget(self.clear_files_button)
        button_row.addWidget(self.run_button)
        button_row.addWidget(self.run_correl_button)
        button_row.addWidget(self.stop_button)
        button_row.addStretch()
        button_row.addWidget(self.scatty_button)
        layout.addLayout(button_row)

        return group

    # --- browsing / title discovery ----------------------------------------

    def _browse_executable(self) -> None:
        start_dir = ""
        if self._spinvert_path:
            start_dir = str(Path(self._spinvert_path).expanduser().parent)
        path, _ = QFileDialog.getOpenFileName(
            self, "Select spinvert executable", start_dir
        )
        if path:
            self._set_spinvert_path(path, persist=True)

    def _set_spinvert_path(self, path: str, persist: bool) -> None:
        self._spinvert_path = path.strip()
        self.exe_status_label.setText(
            f"spinvert: {self._spinvert_path}"
            if self._spinvert_path
            else "spinvert: not set"
        )
        if persist and self._spinvert_path:
            try:
                where = save_spinvert_path(self._spinvert_path)
            except OSError as exc:
                QMessageBox.warning(
                    self,
                    "Could not save setting",
                    f"The spinvert executable path could not be saved:\n{exc}",
                )
            else:
                self._append_log(f"Saved spinvert executable path to {where}\n")

    def _verify_executable_configured(self) -> None:
        """On startup, make sure a usable spinvert executable is configured.

        If nothing has ever been configured (first run), offer to download
        and build the whole SpinHarmony toolchain automatically. Otherwise,
        if a path was configured but no longer resolves, just point the user
        at the menu to fix it.
        """
        if not self._spinvert_path:
            self._offer_auto_setup()
            return
        if resolve_executable(self._spinvert_path) is None:
            QMessageBox.warning(
                self,
                "spinvert executable not found",
                "The saved spinvert executable no longer exists:\n\n"
                f"{self._spinvert_path}\n\n"
                "Choose it again via  File → "
                "“Set spinvert executable…”  before running spinvert.",
            )

    def _offer_auto_setup(self) -> None:
        answer = QMessageBox.question(
            self,
            "spinvert executable not set",
            "No SpinHarmony executables are configured "
            f"(nothing saved in {settings_file()}).\n\n"
            "Would you like to automatically download and build them now?\n\n"
            "(Alternatively, choose an existing executable via  File → "
            "“Set spinvert executable…”.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        if not gfortran_available():
            QMessageBox.warning(
                self,
                "gfortran not found",
                "Building SpinHarmony requires gfortran, which isn't on your "
                "PATH.\n\n"
                "Install it (e.g. via your system package manager, or from "
                "https://gcc.gnu.org/wiki/GFortranBinaries) and then reopen "
                "this dialog via  File → “Set spinvert executable…”.",
            )
            return

        self._start_auto_setup()

    def _start_auto_setup(self) -> None:
        if self._setup_worker is not None and self._setup_worker.isRunning():
            return
        self.run_action.setEnabled(False)
        self.run_correl_action.setEnabled(False)
        self.status_label.setText("Downloading and building SpinHarmony...")
        self._append_log("Downloading and building SpinHarmony...\n")

        worker = SetupWorker(self)
        worker.progress.connect(self._append_log)
        worker.succeeded.connect(self._on_setup_succeeded)
        worker.failed.connect(self._on_setup_failed)
        self._setup_worker = worker
        worker.start()

    def _on_setup_succeeded(self, executables: dict[str, Path]) -> None:
        self._setup_worker = None
        self.run_action.setEnabled(True)
        self.run_correl_action.setEnabled(True)
        self.status_label.setText("SpinHarmony setup complete.")

        spinvert_path = executables.get("spinvert")
        if spinvert_path is not None:
            self._set_spinvert_path(str(spinvert_path), persist=False)
        spincorrel_path = executables.get("spincorrel")
        if spincorrel_path is not None:
            self._set_spincorrel_path(str(spincorrel_path), persist=False)
        scatty_path = executables.get("scatty")
        if scatty_path is not None:
            self._set_scatty_path(str(scatty_path), persist=False)

        QMessageBox.information(
            self,
            "SpinHarmony setup complete",
            "All SpinHarmony components were downloaded and built successfully.",
        )

    def _on_setup_failed(self, message: str) -> None:
        self._setup_worker = None
        self.run_action.setEnabled(True)
        self.run_correl_action.setEnabled(True)
        self.status_label.setText("SpinHarmony setup failed.")
        self._append_log(f"SpinHarmony setup failed: {message}\n")
        QMessageBox.critical(
            self,
            "SpinHarmony setup failed",
            f"Downloading/building SpinHarmony failed:\n\n{message}\n\n"
            "You can set an existing executable via  File → "
            "“Set spinvert executable…”  instead.",
        )

    def _browse_scatty(self) -> None:
        start_dir = ""
        for candidate in (
            self._scatty_path,
            self._spinvert_path,
            self._spincorrel_path,
        ):
            if candidate:
                start_dir = str(Path(candidate).expanduser().parent)
                break
        path, _ = QFileDialog.getOpenFileName(
            self, "Select scatty executable", start_dir
        )
        if path:
            self._set_scatty_path(path, persist=True)

    def _set_scatty_path(self, path: str, persist: bool) -> None:
        self._scatty_path = path.strip()
        self.scatty_status_label.setText(
            f"scatty: {self._scatty_path}" if self._scatty_path else "scatty: not set"
        )
        if persist and self._scatty_path:
            try:
                where = save_scatty_path(self._scatty_path)
            except OSError as exc:
                QMessageBox.warning(
                    self,
                    "Could not save setting",
                    f"The scatty executable path could not be saved:\n{exc}",
                )
            else:
                self._append_log(f"Saved scatty executable path to {where}\n")

    def _open_scatty_window(self) -> None:
        """Open (or raise) the Scatty configuration window, seeding it with the
        current working directory."""
        from spinharmony_studio.scatty.gui.scatty_window import ScattyWindow

        window = self._scatty_window
        if not isinstance(window, ScattyWindow):
            window = ScattyWindow()
            self._scatty_window = window
        workdir = self._current_workdir()
        if workdir is not None:
            window.set_working_directory(str(workdir), self._current_title() or None)
        window.show()
        window.raise_()
        window.activateWindow()

    def _browse_spincorrel(self) -> None:
        start_dir = ""
        for candidate in (self._spincorrel_path, self._spinvert_path):
            if candidate:
                start_dir = str(Path(candidate).expanduser().parent)
                break
        path, _ = QFileDialog.getOpenFileName(
            self, "Select spincorrel executable", start_dir
        )
        if path:
            self._set_spincorrel_path(path, persist=True)

    def _set_spincorrel_path(self, path: str, persist: bool) -> None:
        self._spincorrel_path = path.strip()
        self.correl_status_label.setText(
            f"spincorrel: {self._spincorrel_path}"
            if self._spincorrel_path
            else "spincorrel: not set"
        )
        if persist and self._spincorrel_path:
            try:
                where = save_spincorrel_path(self._spincorrel_path)
            except OSError as exc:
                QMessageBox.warning(
                    self,
                    "Could not save setting",
                    f"The spincorrel executable path could not be saved:\n{exc}",
                )
            else:
                self._append_log(f"Saved spincorrel executable path to {where}\n")

    def _browse_workdir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select working directory")
        if path:
            self.workdir_edit.setText(path)
            self._refresh_titles(path)

    def _refresh_titles(self, workdir: str, select: str | None = None) -> None:
        titles = discover_titles(Path(workdir))
        wanted = select if select is not None else self.title_combo.currentText()
        self.title_combo.blockSignals(True)
        self.title_combo.clear()
        self.title_combo.addItems(titles)
        if wanted and wanted in titles:
            self.title_combo.setCurrentText(wanted)
        elif wanted:
            # keep a remembered title even if its data file is missing
            self.title_combo.setEditText(wanted)
        elif titles:
            self.title_combo.setCurrentIndex(0)
        self.title_combo.blockSignals(False)
        self._on_title_changed()

    def _on_title_changed(self) -> None:
        self._reset_file_tracking()
        self._maybe_autoload_config()
        self._poll_files()

    def _reset_file_tracking(self) -> None:
        self._last_data_mtime = None
        self._last_fit_path = None
        self._last_fit_mtime = None
        self._last_chi_path = None
        self._last_chi_mtime = None
        self._last_scf_path = None
        self._last_scf_mtime = None

    # --- config save / load -------------------------------------------------

    def _current_title(self) -> str:
        return self.title_combo.currentText().strip()

    def _current_workdir(self) -> Path | None:
        text = self.workdir_edit.text().strip()
        if not text:
            return None
        path = Path(text)
        return path if path.is_dir() else None

    def _save_config(self) -> SpinvertConfig | None:
        title = self._current_title()
        workdir = self._current_workdir()
        if not title:
            QMessageBox.warning(self, "No title", "Enter or select a title first.")
            return None
        if workdir is None:
            QMessageBox.warning(
                self, "No working directory", "Select a valid working directory first."
            )
            return None

        config = self.config_form.try_build_config(title, self)
        if config is None:
            return None

        config.save_to_file(config_file_path(workdir, title))
        self._append_log(f"Wrote {config_file_path(workdir, title)}\n")
        return config

    def _load_config(self) -> None:
        workdir = self._current_workdir()
        if workdir is None:
            # No working directory yet: pick a config file anywhere and adopt
            # its folder as the working directory.
            self._load_config_via_browser()
            return

        title = self._current_title()
        if not title:
            QMessageBox.warning(self, "No title", "Select or enter a title first.")
            return

        path = config_file_path(workdir, title)
        if not path.exists():
            QMessageBox.warning(self, "Not found", f"{path} does not exist.")
            return

        self._load_config_file(path, quiet=False)

    def _load_config_via_browser(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Select a spinvert config file",
            self.workdir_edit.text().strip(),
            "Spinvert config (*_config.txt);;All files (*)",
        )
        if not path_str:
            return

        path = Path(path_str)
        workdir = path.parent
        if path.name.endswith("_config.txt"):
            title = path.name[: -len("_config.txt")]
        else:
            title = path.stem

        self.workdir_edit.setText(str(workdir))
        self.title_combo.blockSignals(True)
        self.title_combo.clear()
        self.title_combo.addItems(discover_titles(workdir))
        self.title_combo.setCurrentText(title)
        self.title_combo.blockSignals(False)
        self._reset_file_tracking()

        self._load_config_file(path, quiet=False)
        self._poll_files()

    def _maybe_autoload_config(self) -> None:
        """Load [title]_config.txt from the working directory if it is there,
        so switching to an existing dataset picks up its saved settings."""
        title = self._current_title()
        workdir = self._current_workdir()
        if not title or workdir is None:
            return
        path = config_file_path(workdir, title)
        if path.exists():
            self._load_config_file(path, quiet=True)

    def _load_config_file(self, path: Path, quiet: bool) -> None:
        try:
            config = SpinvertConfig.from_file(path)
        except Exception as exc:
            if quiet:
                self._append_log(f"Could not auto-load {path}: {exc}\n")
            else:
                QMessageBox.critical(self, "Failed to load config", str(exc))
            return

        self.config_form.load_config(config)
        self._append_log(f"Loaded {path}\n")

    def _view_config(self) -> None:
        title = self._current_title()
        workdir = self._current_workdir()
        if not title or workdir is None:
            QMessageBox.warning(
                self, "Nothing to view", "Select a working directory and title first."
            )
            return

        path = config_file_path(workdir, title)
        if not path.exists():
            QMessageBox.warning(
                self, "Not found", f"{path} does not exist yet. Save the config first."
            )
            return

        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            QMessageBox.warning(
                self,
                "Could not open",
                f"The operating system could not open {path} in a text editor.",
            )

    def _clear_generated_files(self) -> None:
        title = self._current_title()
        workdir = self._current_workdir()
        if not title or workdir is None:
            QMessageBox.warning(
                self, "Nothing to clear", "Select a working directory and title first."
            )
            return
        if self.runner.is_running():
            QMessageBox.warning(
                self,
                "spinvert is running",
                "Stop the running spinvert process before clearing its output files.",
            )
            return

        files = generated_output_files(workdir, title)
        if not files:
            QMessageBox.information(
                self,
                "Nothing to clear",
                f"No spinvert output files found for {title!r} in {workdir}.",
            )
            return

        listing = "\n".join(f"    {p.name}" for p in files)
        reply = QMessageBox.question(
            self,
            "Delete generated files?",
            f"Permanently delete these {len(files)} file(s) that spinvert "
            f"generated for {title!r}?\n\n{listing}\n\n"
            "The input files ([title]_data.txt and [title]_config.txt) are kept. "
            "This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        deleted = 0
        errors: list[str] = []
        for path in files:
            try:
                path.unlink()
                deleted += 1
            except OSError as exc:
                errors.append(f"{path.name}: {exc}")

        self._append_log(f"Deleted {deleted} generated file(s) for {title}.\n")
        if errors:
            joined = "\n  ".join(errors)
            self._append_log(f"Could not delete:\n  {joined}\n")
            QMessageBox.warning(self, "Some files not deleted", joined)

        # Plots/status were showing results that no longer exist.
        self._fit = None
        self._fit_label = None
        self._scf = None
        self._reset_file_tracking()
        self._redraw_data_and_fit()
        self.correl_panel.update_scf(None)
        self.status_label.setText("Cleared generated files.")

    # --- running spinvert -----------------------------------------------------

    def _prepare_executable(self, path: str, label: str) -> str | None:
        return prepare_executable(self, path, label, self._append_log)

    def _run_spinvert(self) -> None:
        if self.runner.is_running() or self.correl_runner.is_running():
            return
        resolved = self._prepare_executable(self._spinvert_path, "spinvert")
        if resolved is None:
            return
        workdir = self._current_workdir()
        if workdir is None:
            QMessageBox.warning(
                self, "No working directory", "Select a valid working directory first."
            )
            return
        title = self._current_title()
        if not title:
            QMessageBox.warning(self, "No title", "Enter or select a title first.")
            return

        config = self.config_form.try_build_config(title, self)
        if config is None:
            return
        path = config_file_path(workdir, title)
        if not confirm_save_before_run(
            self, config, path, SpinvertConfig.from_file, "spinvert", self._append_log
        ):
            return

        self._append_log(f"Running: {resolved} {title}  (cwd={workdir})\n")
        self.runner.start(resolved, title, str(workdir))
        self._update_run_controls()
        self.status_label.setText("Running spinvert...")

    def _run_spincorrel(self) -> None:
        if self.runner.is_running() or self.correl_runner.is_running():
            return
        resolved = self._prepare_executable(self._spincorrel_path, "spincorrel")
        if resolved is None:
            return
        workdir = self._current_workdir()
        if workdir is None:
            QMessageBox.warning(
                self, "No working directory", "Select a valid working directory first."
            )
            return
        title = self._current_title()
        if not title:
            QMessageBox.warning(self, "No title", "Select or enter a title first.")
            return
        if find_latest_numbered_file(workdir, title, "spins") is None:
            reply = QMessageBox.question(
                self,
                "No spin configurations",
                f"No {title}_spins_NN.txt files were found. spincorrel needs the "
                "spin configurations that spinvert writes.\n\nRun spincorrel anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self._append_log(f"Running: {resolved} {title}  (cwd={workdir})\n")
        self.correl_runner.start(resolved, title, str(workdir))
        self._update_run_controls()
        self.status_label.setText("Running spincorrel...")
        if not self.toggle_correl_action.isChecked():
            self.toggle_correl_action.setChecked(True)  # reveal the results blade

    def _stop_running(self) -> None:
        stopped = False
        if self.runner.is_running():
            self._append_log("Stopping spinvert...\n")
            self.runner.stop()
            stopped = True
        if self.correl_runner.is_running():
            self._append_log("Stopping spincorrel...\n")
            self.correl_runner.stop()
            stopped = True
        if not stopped:
            self._append_log("No process is running.\n")
        self._update_run_controls()

    def _save_panel_png(self, panel, path: Path) -> None:
        try:
            panel.save_png(path)
        except Exception as exc:  # matplotlib / OSError
            self._append_log(f"Could not save {path.name}: {exc}\n")
        else:
            self._append_log(f"Saved plot to {path}\n")

    def _on_run_finished(self, exit_code: int) -> None:
        self._append_log(f"spinvert exited with code {exit_code}\n")
        self._update_run_controls()
        self.status_label.setText(f"spinvert finished (exit code {exit_code}).")
        # Snapshot the fit plot, whether spinvert finished on its own or was
        # stopped (Stop -> kill -> this handler still fires).
        workdir = self._current_workdir()
        title = self._current_title()
        if workdir is not None and title:
            self._poll_files()
            self._save_panel_png(self.plot_panel, plot_image_path(workdir, title))

    def _on_correl_finished(self, exit_code: int) -> None:
        self._append_log(f"spincorrel exited with code {exit_code}\n")
        self._update_run_controls()
        self.status_label.setText(f"spincorrel finished (exit code {exit_code}).")
        workdir = self._current_workdir()
        title = self._current_title()
        if workdir is not None and title:
            self._poll_scf(workdir, title)
            if self._scf is not None and self._scf[0].size:
                self._save_panel_png(self.correl_panel, scf_image_path(workdir, title))

    def _update_run_controls(self) -> None:
        busy = self.runner.is_running() or self.correl_runner.is_running()
        self.run_button.setEnabled(not busy)
        self.run_action.setEnabled(not busy)
        self.run_correl_button.setEnabled(not busy)
        self.run_correl_action.setEnabled(not busy)
        self.stop_button.setEnabled(busy)
        self.stop_action.setEnabled(busy)

    def _append_log(self, text: str) -> None:
        self.output_log.append(text)

    # --- polling for updated output files --------------------------------------

    def _poll_files(self) -> None:
        title = self._current_title()
        workdir = self._current_workdir()
        if not title or workdir is None:
            return

        self._poll_data(workdir, title)
        self._poll_fit(workdir, title)
        self._poll_chi(workdir, title)
        self._poll_scf(workdir, title)

    def _poll_data(self, workdir: Path, title: str) -> None:
        path = data_file_path(workdir, title)
        if not path.exists():
            return
        mtime = path.stat().st_mtime
        if mtime == self._last_data_mtime:
            return
        try:
            self._data = parse_data_file(path)
        except OSError:
            return
        self._last_data_mtime = mtime
        self._redraw_data_and_fit()

    def _poll_fit(self, workdir: Path, title: str) -> None:
        path = find_latest_numbered_file(workdir, title, "fit")
        if path is None:
            return
        mtime = path.stat().st_mtime
        if path == self._last_fit_path and mtime == self._last_fit_mtime:
            return
        try:
            self._fit = parse_fit_file(path)
        except OSError:
            return
        self._fit_label = path.stem
        self._last_fit_path = path
        self._last_fit_mtime = mtime
        self._redraw_data_and_fit()

    def _poll_chi(self, workdir: Path, title: str) -> None:
        path = find_latest_numbered_file(workdir, title, "chi")
        if path is None:
            return
        mtime = path.stat().st_mtime
        if path == self._last_chi_path and mtime == self._last_chi_mtime:
            return
        try:
            chi = parse_chi_file(path)
        except OSError:
            return
        self._last_chi_path = path
        self._last_chi_mtime = mtime

        if chi[1].size:
            latest_chi2 = chi[1][-1]
            latest_moves = chi[0][-1]
            self.status_label.setText(
                f"{path.stem}: chi^2 = {latest_chi2:.6g} "
                f"at {latest_moves:.0f} moves/spin"
            )

    def _poll_scf(self, workdir: Path, title: str) -> None:
        path = scf_file_path(workdir, title)
        if not path.exists():
            return
        mtime = path.stat().st_mtime
        if path == self._last_scf_path and mtime == self._last_scf_mtime:
            return
        try:
            self._scf = parse_scf_file(path)
        except OSError:
            return
        self._last_scf_path = path
        self._last_scf_mtime = mtime
        self.correl_panel.update_scf(self._scf, path.stem)

    def _redraw_data_and_fit(self) -> None:
        self.plot_panel.update_data_and_fit(self._data, self._fit, self._fit_label)


def run_spinharmony(args: Sequence[str] | None = None) -> None:
    # Importing spinharmony_studio.settings sets the org/app name that
    # QStandardPaths uses for settings.py's config directory.
    app = QApplication(list(args) if args is not None else sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_spinharmony()
