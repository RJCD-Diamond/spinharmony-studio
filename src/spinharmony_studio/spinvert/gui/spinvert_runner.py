"""Runs an external command-line program (spinvert / spincorrel) as a child
process and streams its merged stdout+stderr."""

from PyQt6.QtCore import QObject, QProcess, pyqtSignal


class SpinvertRunner(QObject):
    output_received = pyqtSignal(str)
    finished = pyqtSignal(int)

    def __init__(
        self, parent: QObject | None = None, *, program_label: str = "spinvert"
    ) -> None:
        super().__init__(parent)
        self._label = program_label
        self._pending_stem: str | None = None
        self._done = True
        self.process = QProcess(self)
        # These programs print a lot of progress text; merge stdout and stderr
        # so the window shows it in the order the program actually wrote it.
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.started.connect(self._on_started)
        self.process.errorOccurred.connect(self._on_error)
        self.process.readyReadStandardOutput.connect(self._on_stdout)
        self.process.readyReadStandardError.connect(self._on_stderr)
        self.process.finished.connect(self._on_finished)

    def start(self, executable: str, title: str, workdir: str) -> None:
        # spinvert / spincorrel / scatty are all invoked as
        # `<program> <input file name stem>`; some builds take the stem as a
        # command-line argument, others prompt for it on stdin, so we supply it
        # both ways (see _on_started).
        self._pending_stem = title or None
        self._done = False
        self.process.setWorkingDirectory(workdir)
        self.process.setProgram(executable)
        self.process.setArguments([title] if title else [])
        self.process.start()

    def _on_started(self) -> None:
        if self._pending_stem is None:
            return
        self.process.write(f"{self._pending_stem}\n".encode())
        self.process.closeWriteChannel()
        self._pending_stem = None

    def stop(self) -> None:
        if self.is_running():
            self.process.kill()

    def is_running(self) -> bool:
        return self.process.state() != QProcess.ProcessState.NotRunning

    def _on_stdout(self) -> None:
        text = self.process.readAllStandardOutput().data().decode(errors="replace")
        if text:
            self.output_received.emit(text)

    def _on_stderr(self) -> None:
        text = self.process.readAllStandardError().data().decode(errors="replace")
        if text:
            self.output_received.emit(text)

    def _error_text(self, error: QProcess.ProcessError) -> str:
        label = self._label
        return {
            QProcess.ProcessError.FailedToStart: (
                f"{label} failed to start. Check that the executable path is "
                "correct, points at a real file, and is marked executable."
            ),
            QProcess.ProcessError.Crashed: f"{label} crashed (or was terminated).",
            QProcess.ProcessError.Timedout: f"{label} timed out.",
            QProcess.ProcessError.WriteError: f"Could not write to {label}'s stdin.",
            QProcess.ProcessError.ReadError: f"Could not read {label}'s output.",
        }.get(error, f"{label} process error: {error}")

    def _on_error(self, error: QProcess.ProcessError) -> None:
        if self._done:
            return  # a post-run WriteError/ReadError once the child has exited
        detail = self.process.errorString()
        message = self._error_text(error)
        if detail and detail.lower() not in message.lower():
            message = f"{message}\n(Qt: {detail})"
        self.output_received.emit(message + "\n")
        if error == QProcess.ProcessError.FailedToStart:
            # No "finished" will follow a failed start; unstick the UI now.
            self._emit_finished(-1)

    def _on_finished(self, exit_code: int, _exit_status: object) -> None:
        self._emit_finished(exit_code)

    def _emit_finished(self, exit_code: int) -> None:
        if self._done:
            return
        self._done = True
        self.finished.emit(exit_code)
