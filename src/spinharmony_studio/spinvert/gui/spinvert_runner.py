"""Runs the external spinvert executable as a child process."""

from PyQt6.QtCore import QObject, QProcess, pyqtSignal


class SpinvertRunner(QObject):
    output_received = pyqtSignal(str)
    finished = pyqtSignal(int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.process = QProcess(self)
        # spinvert prints a lot of progress text; merge stdout and stderr so
        # the window shows it in the order the program actually wrote it.
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._on_stdout)
        self.process.readyReadStandardError.connect(self._on_stderr)
        self.process.finished.connect(self._on_finished)

    def start(self, executable: str, title: str, workdir: str) -> None:
        self.process.setWorkingDirectory(workdir)
        self.process.setProgram(executable)
        self.process.setArguments([title])
        self.process.start()

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

    def _on_finished(self, exit_code: int, _exit_status: object) -> None:
        self.finished.emit(exit_code)
