"""Scatty configuration window: edit a scatty_config.txt, run Scatty, and view
its output. Built entirely from components shared with the spinvert GUI
(blades, output log, process runner, executable helpers, mpl panels).

Can be launched on its own (``python -m spinharmony_studio.scatty.gui.app``) or
opened from the spinvert window, which seeds the working directory.
"""

import sys
from collections.abc import Sequence
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QAction, QDesktopServices
from PyQt6.QtWidgets import (
    QApplication,
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

from spinharmony_studio.scatty.config import ScattyConfig
from spinharmony_studio.scatty.gui.scatty_form import ScattyConfigForm
from spinharmony_studio.scatty.gui.scatty_plot_panel import ScattyPlotPanel
from spinharmony_studio.settings import (
    load_scatty_path,
    save_scatty_path,
    settings_file,
)
from spinharmony_studio.spinvert.gui.blade_splitter import BladeSplitter
from spinharmony_studio.spinvert.gui.config_prompt import confirm_save_before_run
from spinharmony_studio.spinvert.gui.executables import (
    prepare_executable,
    resolve_executable,
)
from spinharmony_studio.spinvert.gui.output_log import OutputLog
from spinharmony_studio.spinvert.gui.spinvert_runner import SpinvertRunner

__all__ = ["ScattyWindow", "main"]

_CONFIG_NAME = "scatty_config.txt"
POLL_INTERVAL_MS = 1000


class ScattyWindow(QMainWindow):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Scatty configuration")
        self.resize(1300, 850)

        self.runner = SpinvertRunner(self, program_label="scatty")
        self.runner.output_received.connect(self._append_log)
        self.runner.finished.connect(self._on_finished)

        self._scatty_path: str = ""
        self._last_output: Path | None = None
        self._last_output_mtime: float | None = None
        self._checked_executable = False

        # The input-file stem (matches the spinvert title / the atoms+spins
        # files) is separate from the config's NAME; it lives in the top bar,
        # NAME lives in the form and feeds the output filenames.
        self.stem_edit = QLineEdit()
        self.stem_edit.setPlaceholderText(
            "input-file stem: <stem>_atoms_NN.txt / <stem>_spins_NN.txt"
        )
        self.config_form = ScattyConfigForm()

        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.addWidget(self._build_workdir_group())

        self.form_scroll = QScrollArea()
        self.form_scroll.setWidgetResizable(True)
        self.form_scroll.setWidget(self.config_form)

        self.output_log = OutputLog("Scatty output")
        self.plot_panel = ScattyPlotPanel()

        # Keep the plot's colourmap / intensity range in step with the config
        # form, so the <stem>_sc.txt grid is drawn the way Scatty rendered it.
        form = self.config_form
        form.ppm_cmap_combo.currentTextChanged.connect(self._push_ppm_style)
        form.ppm_output_cb.toggled.connect(self._push_ppm_style)
        form.ppm_min.valueChanged.connect(self._push_ppm_style)
        form.ppm_max.valueChanged.connect(self._push_ppm_style)
        # Quick 2-D slice buttons fill the form, then ask to run.
        form.run_requested.connect(self._run_scatty)

        # Two blades: configuration (left) and the scattering plot (right).
        self.blades = BladeSplitter(
            left=self.form_scroll,
            left_label="Configuration",
            right=self.plot_panel,
            right_label="Scattering plot",
            left_visible=True,
            right_visible=True,
        )
        self.blades.left_toggled.connect(
            lambda v: self._sync_toggle(self.toggle_config_action, v)
        )
        self.blades.right_toggled.connect(
            lambda v: self._sync_toggle(self.toggle_plot_action, v)
        )

        # The output log spans the full window width below the blades.
        self.body_splitter = QSplitter()
        self.body_splitter.setOrientation(Qt.Orientation.Vertical)
        self.body_splitter.addWidget(self.blades)
        self.body_splitter.addWidget(self.output_log)
        self.body_splitter.setStretchFactor(0, 4)
        self.body_splitter.setStretchFactor(1, 1)
        outer.addWidget(self.body_splitter, stretch=1)
        self._did_initial_split = False

        self._build_menu_bar()

        self.status_label = QLabel("No run in progress.")
        status_bar = self.statusBar()
        assert status_bar is not None
        status_bar.addWidget(self.status_label)
        self.scatty_status_label = QLabel()
        status_bar.addPermanentWidget(self.scatty_status_label)

        self._set_scatty_path(load_scatty_path() or "", persist=False)

        self.timer = QTimer(self)
        self.timer.setInterval(POLL_INTERVAL_MS)
        self.timer.timeout.connect(self._poll_output)
        self.timer.start()

    # --- construction ---------------------------------------------------

    def _build_workdir_group(self) -> QGroupBox:
        group = QGroupBox("Working directory")
        layout = QVBoxLayout(group)

        row = QHBoxLayout()
        self.workdir_edit = QLineEdit()
        self.workdir_edit.setPlaceholderText(
            "Directory Scatty runs in (scatty_config.txt is written here)"
        )
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse_workdir)
        row.addWidget(QLabel("Working directory"))
        row.addWidget(self.workdir_edit, stretch=1)
        row.addWidget(browse)
        layout.addLayout(row)

        # The input-file stem (usually the spinvert title); NAME is edited in
        # the form and only affects Scatty's output filenames.
        stem_row = QHBoxLayout()
        stem_row.addWidget(QLabel("Input file stem"))
        stem_row.addWidget(self.stem_edit, stretch=1)
        layout.addLayout(stem_row)

        buttons = QHBoxLayout()
        self.save_button = QPushButton("Save config")
        self.load_button = QPushButton("Load config")
        self.view_button = QPushButton("View config file")
        self.run_button = QPushButton("Run scatty")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.save_button.clicked.connect(self._save_config)
        self.load_button.clicked.connect(self._load_config)
        self.view_button.clicked.connect(self._view_config)
        self.run_button.clicked.connect(self._run_scatty)
        self.stop_button.clicked.connect(self._stop)
        for b in (
            self.save_button,
            self.load_button,
            self.view_button,
            self.run_button,
            self.stop_button,
        ):
            buttons.addWidget(b)
        buttons.addStretch()
        layout.addLayout(buttons)
        return group

    def _build_menu_bar(self) -> None:
        menu_bar = self.menuBar()
        assert menu_bar is not None

        file_menu = menu_bar.addMenu("&File")
        assert file_menu is not None
        self._add_action(file_menu, "Set sca&tty executable...", self._browse_scatty)
        file_menu.addSeparator()
        self._add_action(file_menu, "&Save config", self._save_config, "Ctrl+S")
        self._add_action(file_menu, "&Load config", self._load_config, "Ctrl+O")
        self._add_action(file_menu, "&View config file", self._view_config)
        file_menu.addSeparator()
        self.run_action = self._add_action(
            file_menu, "&Run scatty", self._run_scatty, "Ctrl+R"
        )
        self.stop_action = self._add_action(file_menu, "Sto&p", self._stop)
        self.stop_action.setEnabled(False)
        file_menu.addSeparator()
        self._add_action(file_menu, "&Close", self.close, "Ctrl+W")

        edit_menu = menu_bar.addMenu("&Edit")
        assert edit_menu is not None
        self._add_action(
            edit_menu, "&Copy output", self.output_log.copy_all, "Ctrl+Shift+C"
        )
        self._add_action(edit_menu, "Clear &output", self.output_log.clear)

        view_menu = menu_bar.addMenu("&View")
        assert view_menu is not None
        self.toggle_config_action = QAction("Show &configuration panel", self)
        self.toggle_config_action.setCheckable(True)
        self.toggle_config_action.setChecked(True)
        self.toggle_config_action.setShortcut("F9")
        self.toggle_config_action.toggled.connect(self.blades.set_left_visible)
        view_menu.addAction(self.toggle_config_action)

        self.toggle_plot_action = QAction("Show scattering &plot panel", self)
        self.toggle_plot_action.setCheckable(True)
        self.toggle_plot_action.setChecked(True)
        self.toggle_plot_action.setShortcut("F10")
        self.toggle_plot_action.toggled.connect(self.blades.set_right_visible)
        view_menu.addAction(self.toggle_plot_action)

    def _add_action(self, menu, text, slot, shortcut: str | None = None) -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(shortcut)
        action.triggered.connect(lambda: slot())
        menu.addAction(action)
        return action

    @staticmethod
    def _sync_toggle(action: QAction, checked: bool) -> None:
        if action.isChecked() != checked:
            action.blockSignals(True)
            action.setChecked(checked)
            action.blockSignals(False)

    def showEvent(self, a0) -> None:  # noqa: N802 (Qt override)
        super().showEvent(a0)
        if not self._did_initial_split:
            self._did_initial_split = True
            height = self.body_splitter.height()
            if height > 0:
                blades_h = round(height * 0.72)
                self.body_splitter.setSizes([blades_h, height - blades_h])
        if not self._checked_executable:
            self._checked_executable = True
            self._verify_executable_configured()

    # --- public API (used by the spinvert window) ----------------------

    def set_working_directory(self, path: str, stem: str | None = None) -> None:
        changed = path != self.workdir_edit.text().strip()
        self.workdir_edit.setText(path)
        if changed:
            if stem:
                self.stem_edit.setText(stem)
            # An existing scatty_config.txt in the folder wins over the seed.
            self._maybe_autoload_config()
        self._poll_output(force=True)

    # --- working directory --------------------------------------------

    def _current_stem(self) -> str:
        return self.stem_edit.text().strip()

    def _browse_workdir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select working directory")
        if path:
            self.workdir_edit.setText(path)
            self._maybe_autoload_config()
            self._poll_output(force=True)

    def _maybe_autoload_config(self) -> None:
        """Load scatty_config.txt from the working directory if it is there."""
        workdir = self._current_workdir()
        if workdir is None:
            return
        path = self._config_path(workdir)
        if path.is_file():
            self._load_config_file(path, quiet=True)

    # --- helpers -----------------------------------------------------

    def _append_log(self, text: str) -> None:
        self.output_log.append(text)

    def _current_workdir(self) -> Path | None:
        text = self.workdir_edit.text().strip()
        if not text:
            return None
        path = Path(text)
        return path if path.is_dir() else None

    def _config_path(self, workdir: Path) -> Path:
        return workdir / _CONFIG_NAME

    # --- executable --------------------------------------------------

    def _browse_scatty(self) -> None:
        start_dir = (
            str(Path(self._scatty_path).expanduser().parent)
            if self._scatty_path
            else ""
        )
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

    def _verify_executable_configured(self) -> None:
        if not self._scatty_path:
            QMessageBox.warning(
                self,
                "scatty executable not set",
                "No scatty executable is configured "
                f"(nothing saved in {settings_file()}).\n\n"
                "Choose it via  File → “Set scatty executable…”  before running.",
            )
        elif resolve_executable(self._scatty_path) is None:
            QMessageBox.warning(
                self,
                "scatty executable not found",
                f"The saved scatty executable no longer exists:\n\n{self._scatty_path}",
            )

    # --- config save / load / view --------------------------------

    def _save_config(self) -> ScattyConfig | None:
        workdir = self._current_workdir()
        if workdir is None:
            QMessageBox.warning(
                self, "No working directory", "Select a valid working directory first."
            )
            return None
        config = self.config_form.try_build_config(self)
        if config is None:
            return None
        path = self._config_path(workdir)
        config.save_to_file(path)
        self._append_log(f"Wrote {path}\n")
        return config

    def _load_config(self) -> None:
        workdir = self._current_workdir()
        start = (
            str(workdir) if workdir is not None else self.workdir_edit.text().strip()
        )
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Select a scatty config file",
            start,
            "Scatty config (scatty_config.txt);;All files (*)",
        )
        if not path_str:
            return
        path = Path(path_str)
        self.workdir_edit.setText(str(path.parent))
        self._load_config_file(path, quiet=False)

    def _load_config_file(self, path: Path, quiet: bool) -> None:
        try:
            config = ScattyConfig.from_file(path)
        except Exception as exc:
            if quiet:
                self._append_log(f"Could not auto-load {path}: {exc}\n")
            else:
                QMessageBox.critical(self, "Failed to load config", str(exc))
            return
        self.config_form.load_config(config)
        self._push_ppm_style()
        self._append_log(f"Loaded {path}\n")

    def _view_config(self) -> None:
        workdir = self._current_workdir()
        if workdir is None:
            QMessageBox.warning(
                self, "No working directory", "Select a valid working directory first."
            )
            return
        path = self._config_path(workdir)
        if not path.exists():
            QMessageBox.warning(
                self, "Not found", f"{path} does not exist yet. Save the config first."
            )
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            QMessageBox.warning(
                self, "Could not open", f"The OS could not open {path}."
            )

    # --- running scatty -------------------------------------------

    def _run_scatty(self) -> None:
        if self.runner.is_running():
            return
        resolved = prepare_executable(
            self, self._scatty_path, "scatty", self._append_log
        )
        if resolved is None:
            return
        workdir = self._current_workdir()
        if workdir is None:
            QMessageBox.warning(
                self, "No working directory", "Select a valid working directory first."
            )
            return
        stem = self._current_stem()
        if not stem:
            QMessageBox.warning(
                self,
                "No input stem",
                "Enter an input file stem. Scatty is run as  ./scatty <stem>  "
                "and reads <stem>_atoms_NN.txt / <stem>_spins_NN.txt from the "
                "working directory.",
            )
            return
        if not any(workdir.glob(f"{stem}_atoms_*.txt")) and not any(
            workdir.glob(f"{stem}_spins_*.txt")
        ):
            reply = QMessageBox.question(
                self,
                "No atoms/spins files",
                f"No {stem}_atoms_NN.txt or {stem}_spins_NN.txt files were found in "
                f"{workdir}.\n\nRun scatty anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        try:
            config, config_warnings = self.config_form.build_config_with_warnings()
        except Exception as exc:  # pydantic.ValidationError or ValueError
            QMessageBox.critical(self, "Invalid scatty configuration", str(exc))
            return
        if config_warnings:
            reply = QMessageBox.question(
                self,
                "Scatty configuration warning",
                "Scatty is likely to abort or skip the .ppm for this "
                "configuration:\n\n" + "\n\n".join(config_warnings) + "\n\nRun anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        if not confirm_save_before_run(
            self,
            config,
            self._config_path(workdir),
            ScattyConfig.from_file,
            "scatty",
            self._append_log,
        ):
            return

        # scatty reads scatty_config.txt from the cwd; the stem is argv[1].
        self._append_log(f"Running: {resolved} {stem}  (cwd={workdir})\n")
        self.runner.start(resolved, stem, str(workdir))
        self._set_running(True)
        self.status_label.setText("Running scatty...")
        if not self.toggle_plot_action.isChecked():
            self.toggle_plot_action.setChecked(True)

    def _stop(self) -> None:
        if self.runner.is_running():
            self._append_log("Stopping scatty...\n")
            self.runner.stop()
        else:
            self._append_log("No scatty process is running.\n")
        self._set_running(False)

    def _on_finished(self, exit_code: int) -> None:
        self._append_log(f"scatty exited with code {exit_code}\n")
        self._set_running(False)
        self.status_label.setText(f"scatty finished (exit code {exit_code}).")
        workdir = self._current_workdir()
        self._poll_output(force=True)
        if self._last_output is not None and workdir is not None:
            stem = self._current_stem() or "scatty"
            png = workdir / f"{stem}_scatty.png"
            try:
                self.plot_panel.save_png(png)
            except Exception as exc:  # matplotlib / OSError
                self._append_log(f"Could not save {png.name}: {exc}\n")
            else:
                self._append_log(f"Saved plot to {png}\n")

    def _set_running(self, running: bool) -> None:
        self.run_button.setEnabled(not running)
        self.run_action.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self.stop_action.setEnabled(running)

    # --- output polling ----------------------------------------

    def _push_ppm_style(self) -> None:
        """Forward the form's PPM colourmap / range to the plot panel so the
        ``<stem>_sc.txt`` grid is drawn the way Scatty rendered its ``.ppm``."""
        form = self.config_form
        text = form.ppm_cmap_combo.currentText().strip()
        colourmap = None if text in ("", "(none)") else text
        ppm_range = (
            (form.ppm_min.value(), form.ppm_max.value())
            if form.ppm_output_cb.isChecked()
            else None
        )
        self.plot_panel.set_ppm_style(colourmap, ppm_range)

    @staticmethod
    def _newest(paths: "list[Path]") -> tuple[Path | None, float]:
        best: Path | None = None
        best_mtime = -1.0
        for path in paths:
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if mtime > best_mtime:
                best, best_mtime = path, mtime
        return best, best_mtime

    def _poll_output(self, force: bool = False) -> None:
        workdir = self._current_workdir()
        if workdir is None:
            return
        stem = self._current_stem()

        def _sc_ppm(pattern: str) -> list[Path]:
            return [
                p
                for p in sorted(workdir.glob(pattern))
                if not p.name.endswith("_colourbar.ppm")
            ]

        # Only genuine Scatty scattering output, most useful first: the 2-D
        # grid (drawn with the configured colourmap + a Python colour bar),
        # then a rendered image. Anything else in the folder (envelope / fit /
        # data files, spinvert plots) is deliberately ignored.
        groups: list[list[Path]] = []
        if stem:
            groups.append(sorted(workdir.glob(f"{stem}_*_sc.txt")))
            groups.append(_sc_ppm(f"{stem}_*_sc.ppm"))
        groups.append(sorted(workdir.glob("*_sc.txt")))
        groups.append(_sc_ppm("*_sc.ppm"))

        latest: Path | None = None
        latest_mtime = -1.0
        for group in groups:
            latest, latest_mtime = self._newest(group)
            if latest is not None:
                break
        if latest is None:
            return
        if (
            not force
            and latest == self._last_output
            and latest_mtime == (self._last_output_mtime or -1.0)
        ):
            return
        self._last_output = latest
        self._last_output_mtime = latest_mtime
        self._push_ppm_style()
        self.plot_panel.show_output(latest)


def main(args: Sequence[str] | None = None) -> None:
    app = QApplication(list(args) if args is not None else sys.argv)
    app.setOrganizationName("DiamondLightSource")
    app.setApplicationName("spinharmony-studio")
    window = ScattyWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
