"""Main window: config editor + spinvert runner + live fit/chi plots."""

from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QAction, QDesktopServices, QFontDatabase, QTextCursor
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from spinharmony_studio.spinvert.config import SpinvertConfig
from spinharmony_studio.spinvert.gui.config_form import ConfigFormWidget
from spinharmony_studio.spinvert.gui.data_files import (
    config_file_path,
    data_file_path,
    discover_titles,
    find_latest_numbered_file,
    parse_chi_file,
    parse_data_file,
)
from spinharmony_studio.spinvert.gui.plot_panel import PlotPanel
from spinharmony_studio.spinvert.gui.spinvert_runner import SpinvertRunner

POLL_INTERVAL_MS = 1000


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Spinvert Studio")
        self.resize(1400, 900)

        self.runner = SpinvertRunner(self)
        self.runner.output_received.connect(self._append_log)
        self.runner.finished.connect(self._on_run_finished)

        self._build_menu_bar()

        self._last_data_mtime: float | None = None
        self._last_fit_path: Path | None = None
        self._last_fit_mtime: float | None = None
        self._last_chi_path: Path | None = None
        self._last_chi_mtime: float | None = None
        self._data: tuple | None = None
        self._fit: tuple | None = None
        self._fit_label: str | None = None

        central = QWidget()
        self.setCentralWidget(central)
        outer_layout = QVBoxLayout(central)
        outer_layout.addWidget(self._build_program_group())

        self.main_splitter = QSplitter()
        self.main_splitter.setChildrenCollapsible(True)
        outer_layout.addWidget(self.main_splitter, stretch=1)

        self.config_form = ConfigFormWidget()
        self.form_scroll = QScrollArea()
        self.form_scroll.setWidgetResizable(True)
        self.form_scroll.setWidget(self.config_form)
        self.main_splitter.addWidget(self.form_scroll)

        right_splitter = QSplitter()
        right_splitter.setOrientation(Qt.Orientation.Vertical)
        self.plot_panel = PlotPanel()
        right_splitter.addWidget(self.plot_panel)

        right_splitter.addWidget(self._build_output_group())
        right_splitter.setStretchFactor(0, 3)
        right_splitter.setStretchFactor(1, 2)

        self.main_splitter.addWidget(right_splitter)
        # Config panel and plot each take half the window by default.
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 1)
        self._did_initial_split = False
        self._saved_splitter_sizes: list[int] | None = None

        self.status_label = QLabel("No run in progress.")
        status_bar = self.statusBar()
        assert status_bar is not None
        status_bar.addWidget(self.status_label)

        self.timer = QTimer(self)
        self.timer.setInterval(POLL_INTERVAL_MS)
        self.timer.timeout.connect(self._poll_files)
        self.timer.start()

    # --- layout ----------------------------------------------------------

    def showEvent(self, a0) -> None:  # noqa: N802 (Qt override)
        super().showEvent(a0)
        if not self._did_initial_split:
            self._did_initial_split = True
            width = self.main_splitter.width()
            if width > 0:
                self.main_splitter.setSizes([width // 2, width - width // 2])

    def _toggle_config_panel(self, visible: bool) -> None:
        if visible:
            self.form_scroll.setVisible(True)
            if self._saved_splitter_sizes is not None:
                self.main_splitter.setSizes(self._saved_splitter_sizes)
        else:
            self._saved_splitter_sizes = self.main_splitter.sizes()
            self.form_scroll.setVisible(False)

    # --- menu bar --------------------------------------------------------

    def _build_menu_bar(self) -> None:
        menu_bar = self.menuBar()
        assert menu_bar is not None

        file_menu = menu_bar.addMenu("&File")
        assert file_menu is not None
        self._add_action(file_menu, "&Save config", self._save_config, "Ctrl+S")
        self._add_action(file_menu, "&Load config", self._load_config, "Ctrl+O")
        self._add_action(file_menu, "&View config file", self._view_config)
        file_menu.addSeparator()
        self.run_action = self._add_action(
            file_menu, "&Run spinvert", self._run_spinvert, "Ctrl+R"
        )
        self.stop_action = self._add_action(file_menu, "Sto&p", self._stop_spinvert)
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
        self.toggle_config_action.toggled.connect(self._toggle_config_panel)
        view_menu.addAction(self.toggle_config_action)

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
        self.log_view.selectAll()
        self.log_view.copy()

    def _clear_log(self) -> None:
        self.log_view.clear()

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About Spinvert Studio",
            "Spinvert Studio\n\n"
            "A GUI front-end for building Spinvert config files, launching the "
            "spinvert command-line program, and viewing its fit and difference "
            "output live.",
        )

    # --- program output -------------------------------------------------

    def _build_output_group(self) -> QGroupBox:
        group = QGroupBox("Spinvert output")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(4, 4, 4, 4)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(20000)
        self.log_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.log_view.setFont(
            QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        )
        layout.addWidget(self.log_view)
        return group

    # --- top control bar --------------------------------------------------

    def _build_program_group(self) -> QGroupBox:
        group = QGroupBox("Program and working directory")
        layout = QVBoxLayout(group)

        exe_row = QHBoxLayout()
        self.executable_edit = QLineEdit()
        self.executable_edit.setPlaceholderText("Path to the spinvert executable")
        exe_browse = QPushButton("Browse...")
        exe_browse.clicked.connect(self._browse_executable)
        exe_row.addWidget(QLabel("spinvert executable"))
        exe_row.addWidget(self.executable_edit, stretch=1)
        exe_row.addWidget(exe_browse)
        layout.addLayout(exe_row)

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
        self.run_button = QPushButton("Run spinvert")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.save_button.clicked.connect(self._save_config)
        self.load_button.clicked.connect(self._load_config)
        self.view_config_button.clicked.connect(self._view_config)
        self.run_button.clicked.connect(self._run_spinvert)
        self.stop_button.clicked.connect(self._stop_spinvert)
        button_row.addWidget(self.save_button)
        button_row.addWidget(self.load_button)
        button_row.addWidget(self.view_config_button)
        button_row.addWidget(self.run_button)
        button_row.addWidget(self.stop_button)
        button_row.addStretch()
        layout.addLayout(button_row)

        return group

    # --- browsing / title discovery ----------------------------------------

    def _browse_executable(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select spinvert executable")
        if path:
            self.executable_edit.setText(path)

    def _browse_workdir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select working directory")
        if path:
            self.workdir_edit.setText(path)
            self._refresh_titles(path)

    def _refresh_titles(self, workdir: str) -> None:
        titles = discover_titles(Path(workdir))
        current = self.title_combo.currentText()
        self.title_combo.blockSignals(True)
        self.title_combo.clear()
        self.title_combo.addItems(titles)
        if current in titles:
            self.title_combo.setCurrentText(current)
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

        config.to_file(config_file_path(workdir, title))
        self._append_log(f"Wrote {config_file_path(workdir, title)}\n")
        return config

    def _load_config(self) -> None:
        title = self._current_title()
        workdir = self._current_workdir()
        if not title or workdir is None:
            QMessageBox.warning(
                self, "Nothing to load", "Select a working directory and title first."
            )
            return

        path = config_file_path(workdir, title)
        if not path.exists():
            QMessageBox.warning(self, "Not found", f"{path} does not exist.")
            return

        self._load_config_file(path, quiet=False)

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

    # --- running spinvert -----------------------------------------------------

    def _run_spinvert(self) -> None:
        executable = self.executable_edit.text().strip()
        if not executable:
            QMessageBox.warning(
                self, "No executable", "Select the spinvert executable first."
            )
            return
        workdir = self._current_workdir()
        if workdir is None:
            QMessageBox.warning(
                self, "No working directory", "Select a valid working directory first."
            )
            return

        if self._save_config() is None:
            return

        title = self._current_title()
        self._append_log(f"Running: {executable} {title}  (cwd={workdir})\n")
        self.runner.start(executable, title, str(workdir))
        self._set_running(True)
        self.status_label.setText("Running spinvert...")

    def _stop_spinvert(self) -> None:
        self.runner.stop()

    def _on_run_finished(self, exit_code: int) -> None:
        self._append_log(f"spinvert exited with code {exit_code}\n")
        self._set_running(False)
        self.status_label.setText(f"Finished (exit code {exit_code}).")

    def _set_running(self, running: bool) -> None:
        self.run_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self.run_action.setEnabled(not running)
        self.stop_action.setEnabled(running)

    def _append_log(self, text: str) -> None:
        """Append raw process output, preserving its own line breaks and
        keeping the view scrolled to the bottom unless the user scrolled up."""
        scrollbar = self.log_view.verticalScrollBar()
        at_bottom = scrollbar is None or scrollbar.value() >= scrollbar.maximum() - 4

        cursor = self.log_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)

        if at_bottom and scrollbar is not None:
            scrollbar.setValue(scrollbar.maximum())

    # --- polling for updated output files --------------------------------------

    def _poll_files(self) -> None:
        title = self._current_title()
        workdir = self._current_workdir()
        if not title or workdir is None:
            return

        self._poll_data(workdir, title)
        self._poll_fit(workdir, title)
        self._poll_chi(workdir, title)

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
            self._fit = parse_data_file(path)
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

    def _redraw_data_and_fit(self) -> None:
        self.plot_panel.update_data_and_fit(self._data, self._fit, self._fit_label)
