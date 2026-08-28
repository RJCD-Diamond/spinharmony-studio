"""Main window: config editor + spinvert runner + live fit/chi plots."""

import os
import platform
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QAction, QDesktopServices, QFontDatabase, QTextCursor
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
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from spinharmony_studio.spinvert.config import SpinvertConfig
from spinharmony_studio.spinvert.gui.config_form import ConfigFormWidget
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
from spinharmony_studio.spinvert.gui.plot_panel import PlotPanel
from spinharmony_studio.spinvert.gui.settings import (
    load_executable_path,
    load_spincorrel_path,
    save_executable_path,
    save_spincorrel_path,
    settings_file,
)
from spinharmony_studio.spinvert.gui.spinvert_runner import SpinvertRunner

__all__ = ["main"]

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
        self._executable_path: str = ""
        self._spincorrel_path: str = ""
        self._checked_executable = False

        self._build_menu_bar()

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

        self.main_splitter = QSplitter()
        self.main_splitter.setChildrenCollapsible(True)

        # Xbox-360-"blades" collapse control: a thin full-height strip on the
        # left edge. Left arrowhead slides the config panel away to the left;
        # once collapsed it shows a right arrowhead to bring it back.
        self.collapse_button = QToolButton()
        self.collapse_button.setAutoRaise(True)
        self.collapse_button.setFixedWidth(18)
        self.collapse_button.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding
        )
        self.collapse_button.setText("◀")
        self.collapse_button.setToolTip("Collapse the configuration panel")
        self.collapse_button.clicked.connect(lambda: self.toggle_config_action.toggle())

        # Mirror blade on the right edge for the spincorrel panel (starts
        # collapsed): ◀ = bring it in from the right, ▶ = push it back.
        self.correl_collapse_button = QToolButton()
        self.correl_collapse_button.setAutoRaise(True)
        self.correl_collapse_button.setFixedWidth(18)
        self.correl_collapse_button.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding
        )
        self.correl_collapse_button.setText("◀")
        self.correl_collapse_button.setToolTip("Show the spincorrel panel")
        self.correl_collapse_button.clicked.connect(
            lambda: self.toggle_correl_action.toggle()
        )

        splitter_row = QHBoxLayout()
        splitter_row.setContentsMargins(0, 0, 0, 0)
        splitter_row.setSpacing(0)
        splitter_row.addWidget(self.collapse_button)
        splitter_row.addWidget(self.main_splitter, stretch=1)
        splitter_row.addWidget(self.correl_collapse_button)
        outer_layout.addLayout(splitter_row, stretch=1)

        self.config_form = ConfigFormWidget()
        self.form_scroll = QScrollArea()
        self.form_scroll.setWidgetResizable(True)
        self.form_scroll.setWidget(self.config_form)
        self.main_splitter.addWidget(self.form_scroll)

        self.right_splitter = QSplitter()
        self.right_splitter.setOrientation(Qt.Orientation.Vertical)
        self.plot_panel = PlotPanel()
        self.right_splitter.addWidget(self.plot_panel)

        self.right_splitter.addWidget(self._build_output_group())
        self.right_splitter.setStretchFactor(0, 3)
        self.right_splitter.setStretchFactor(1, 2)

        self.main_splitter.addWidget(self.right_splitter)

        self.correl_panel = CorrelPanel()
        self.correl_panel.setVisible(False)
        self.main_splitter.addWidget(self.correl_panel)

        # The visible panes always share the width equally (see
        # _rebalance_main_splitter); the spincorrel panel is hidden until the
        # user opens its blade.
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setStretchFactor(2, 1)
        self._did_initial_split = False

        self.status_label = QLabel("No run in progress.")
        status_bar = self.statusBar()
        assert status_bar is not None
        status_bar.addWidget(self.status_label)
        self.exe_status_label = QLabel()
        status_bar.addPermanentWidget(self.exe_status_label)
        self.correl_status_label = QLabel()
        status_bar.addPermanentWidget(self.correl_status_label)

        # Restore the external-program paths chosen in a previous session.
        self._set_executable_path(load_executable_path() or "", persist=False)
        self._set_spincorrel_path(load_spincorrel_path() or "", persist=False)

        self.timer = QTimer(self)
        self.timer.setInterval(POLL_INTERVAL_MS)
        self.timer.timeout.connect(self._poll_files)
        self.timer.start()

    # --- layout ----------------------------------------------------------

    def showEvent(self, a0) -> None:  # noqa: N802 (Qt override)
        super().showEvent(a0)
        if not self._did_initial_split:
            self._did_initial_split = True
            self._rebalance_main_splitter()
            height = self.right_splitter.height()
            if height > 0:
                # Plot ~70%, output pane ~30% by default; both fully draggable.
                plot_h = round(height * 0.70)
                self.right_splitter.setSizes([plot_h, height - plot_h])

        if not self._checked_executable:
            self._checked_executable = True
            self._verify_executable_configured()

    def _rebalance_main_splitter(self) -> None:
        """Give every currently-visible pane an equal share of the width
        (2 panes -> 50/50, 3 panes -> thirds). Called whenever a blade opens
        or closes."""
        panes = (self.form_scroll, self.right_splitter, self.correl_panel)
        visible = [i for i, pane in enumerate(panes) if pane.isVisible()]
        if not visible:
            return
        total = self.main_splitter.width()
        if total <= 0:
            total = sum(self.main_splitter.sizes()) or 1000
        each = total // len(visible)
        sizes = [0, 0, 0]
        for i in visible:
            sizes[i] = each
        sizes[visible[-1]] += total - each * len(visible)  # absorb rounding
        self.main_splitter.setSizes(sizes)

    def _set_config_visible(self, visible: bool) -> None:
        self.form_scroll.setVisible(visible)
        self._rebalance_main_splitter()
        self.collapse_button.setText("◀" if visible else "▶")
        self.collapse_button.setToolTip(
            "Collapse the configuration panel"
            if visible
            else "Show the configuration panel"
        )
        self._sync_toggle(self.toggle_config_action, visible)

    def _set_correl_visible(self, visible: bool) -> None:
        self.correl_panel.setVisible(visible)
        self._rebalance_main_splitter()
        self.correl_collapse_button.setText("▶" if visible else "◀")
        self.correl_collapse_button.setToolTip(
            "Collapse the spincorrel panel" if visible else "Show the spincorrel panel"
        )
        self._sync_toggle(self.toggle_correl_action, visible)

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
        self.toggle_config_action.toggled.connect(self._set_config_visible)
        view_menu.addAction(self.toggle_config_action)

        self.toggle_correl_action = QAction("Show spin&correl panel", self)
        self.toggle_correl_action.setCheckable(True)
        self.toggle_correl_action.setChecked(False)
        self.toggle_correl_action.setShortcut("F10")
        self.toggle_correl_action.toggled.connect(self._set_correl_visible)
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
        self.log_view.selectAll()
        self.log_view.copy()

    def _clear_log(self) -> None:
        self.log_view.clear()

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

    # --- program output -------------------------------------------------

    def _build_output_group(self) -> QGroupBox:
        group = QGroupBox("Program output")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(4, 4, 4, 4)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(20000)
        self.log_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.log_view.setFont(
            QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        )
        # Small floor so the splitter handle stays grabbable; the pane is
        # otherwise freely resizable via the splitter.
        self.log_view.setMinimumHeight(60)
        layout.addWidget(self.log_view)
        return group

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
        self.save_button.clicked.connect(self._save_config)
        self.load_button.clicked.connect(self._load_config)
        self.view_config_button.clicked.connect(self._view_config)
        self.clear_files_button.clicked.connect(self._clear_generated_files)
        self.run_button.clicked.connect(self._run_spinvert)
        self.run_correl_button.clicked.connect(self._run_spincorrel)
        self.stop_button.clicked.connect(self._stop_running)
        button_row.addWidget(self.save_button)
        button_row.addWidget(self.load_button)
        button_row.addWidget(self.view_config_button)
        button_row.addWidget(self.clear_files_button)
        button_row.addWidget(self.run_button)
        button_row.addWidget(self.run_correl_button)
        button_row.addWidget(self.stop_button)
        button_row.addStretch()
        layout.addLayout(button_row)

        return group

    # --- browsing / title discovery ----------------------------------------

    def _browse_executable(self) -> None:
        start_dir = ""
        if self._executable_path:
            start_dir = str(Path(self._executable_path).expanduser().parent)
        path, _ = QFileDialog.getOpenFileName(
            self, "Select spinvert executable", start_dir
        )
        if path:
            self._set_executable_path(path, persist=True)

    def _set_executable_path(self, path: str, persist: bool) -> None:
        self._executable_path = path.strip()
        self.exe_status_label.setText(
            f"spinvert: {self._executable_path}"
            if self._executable_path
            else "spinvert: not set"
        )
        if persist and self._executable_path:
            try:
                where = save_executable_path(self._executable_path)
            except OSError as exc:
                QMessageBox.warning(
                    self,
                    "Could not save setting",
                    f"The spinvert executable path could not be saved:\n{exc}",
                )
            else:
                self._append_log(f"Saved spinvert executable path to {where}\n")

    def _verify_executable_configured(self) -> None:
        """On startup, make sure a usable spinvert executable is configured;
        otherwise tell the user to pick one before running anything."""
        if not self._executable_path:
            QMessageBox.warning(
                self,
                "spinvert executable not set",
                "No spinvert executable is configured "
                f"(nothing saved in {settings_file()}).\n\n"
                "Choose it via  File → “Set spinvert executable…”  "
                "before running spinvert.",
            )
            return
        if self._resolve_executable(self._executable_path) is None:
            QMessageBox.warning(
                self,
                "spinvert executable not found",
                "The saved spinvert executable no longer exists:\n\n"
                f"{self._executable_path}\n\n"
                "Choose it again via  File → "
                "“Set spinvert executable…”  before running spinvert.",
            )

    def _browse_spincorrel(self) -> None:
        start_dir = ""
        for candidate in (self._spincorrel_path, self._executable_path):
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

        config.to_file(config_file_path(workdir, title))
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
        """Resolve and sanity-check an executable path, showing a dialog and
        returning None on any problem."""
        path = path.strip()
        if not path:
            QMessageBox.warning(
                self,
                f"No {label} executable",
                f"Choose it via  File → “Set {label} executable…”  first.",
            )
            return None
        resolved = self._resolve_executable(path)
        if resolved is None:
            QMessageBox.warning(
                self,
                "Executable not found",
                f"No file found at {path!r} and nothing by that name on PATH.\n\n"
                f"Point the {label} executable at the compiled binary.",
            )
            return None
        problem = self._diagnose_executable(resolved)
        if problem is not None:
            self._append_log(problem + "\n")
            QMessageBox.warning(self, f"Cannot run {label}", problem)
            return None
        return resolved

    def _run_spinvert(self) -> None:
        if self.runner.is_running() or self.correl_runner.is_running():
            return
        resolved = self._prepare_executable(self._executable_path, "spinvert")
        if resolved is None:
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

    @staticmethod
    def _resolve_executable(executable: str) -> str | None:
        """Locate the executable text as a file path (with ~ expansion) or a
        bare name on PATH. Returns the path, or None if nothing is there."""
        candidate = Path(executable).expanduser()
        if candidate.is_file():
            return str(candidate)
        return shutil.which(executable)

    @staticmethod
    def _diagnose_executable(path: str) -> str | None:
        """Return a human-readable reason the file at ``path`` cannot be exec'd,
        or None if it looks runnable on this machine."""
        p = Path(path)
        try:
            size = p.stat().st_size
        except OSError as exc:
            return f"Cannot read {path}: {exc}"
        if not p.is_file():
            return f"{path} is not a regular file."
        if not os.access(p, os.X_OK):
            return f"{path} is not marked executable. Run:\n\n    chmod +x {path}"
        if size == 0:
            return f"{path} is empty (0 bytes)."

        try:
            head = p.read_bytes()[:64]
        except OSError as exc:
            return f"Cannot read {path}: {exc}"

        if head[:2] == b"MZ":
            return (
                f"{path} looks like a Windows executable (.exe), which cannot "
                "run on this machine. Use a spinvert binary built for "
                f"{platform.system()}."
            )
        if head[:4] == b"\x7fELF":
            e_machine = int.from_bytes(head[18:20], "little")
            elf_arch = {
                0x03: "x86 (32-bit)",
                0x3E: "x86-64",
                0x28: "ARM (32-bit)",
                0xB7: "AArch64",
            }.get(e_machine, f"machine 0x{e_machine:02x}")
            host = platform.machine()
            expected = {
                "x86_64": "x86-64",
                "amd64": "x86-64",
                "aarch64": "AArch64",
                "arm64": "AArch64",
                "i686": "x86 (32-bit)",
                "i386": "x86 (32-bit)",
            }.get(host.lower())
            if expected and expected != elf_arch:
                return (
                    f"{path} is an ELF binary for {elf_arch}, but this machine "
                    f"is {host}. You need a spinvert binary built for {host}."
                )
            return None
        if head[:2] == b"#!":
            interp = head.split(b"\n", 1)[0][2:].strip().split()
            name = interp[0].decode(errors="replace") if interp else ""
            if name and not Path(name).exists() and not shutil.which(name):
                return (
                    f"{path} is a script whose interpreter {name!r} (from its "
                    "'#!' line) was not found."
                )
            return None

        if all(b in (9, 10, 13) or 32 <= b <= 126 for b in head):
            return (
                f"{path} looks like a text file, not a program. Point 'spinvert "
                "executable' at the compiled spinvert binary."
            )
        return (
            f"{path} is not a recognised executable format (no ELF or '#!' "
            "header). It may be corrupt or built for another OS."
        )

    def _stop_running(self) -> None:
        stopped = False
        if self.runner.is_running():
            self._append_log("Stopping spinvert...\n")
            # Snapshot whatever the fit plot is showing right now.
            workdir = self._current_workdir()
            title = self._current_title()
            if workdir is not None and title:
                self._save_panel_png(self.plot_panel, plot_image_path(workdir, title))
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


def main(args: Sequence[str] | None = None) -> None:
    app = QApplication(list(args) if args is not None else sys.argv)
    # Give QStandardPaths a stable per-user config directory for settings.py.
    app.setOrganizationName("DiamondLightSource")
    app.setApplicationName("spinharmony-studio")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
