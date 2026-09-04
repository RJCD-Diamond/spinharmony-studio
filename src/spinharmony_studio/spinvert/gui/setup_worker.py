"""Background thread that downloads and builds the SpinHarmony components.

``setup_spinharmony`` reports progress via plain ``print()`` calls; this
redirects that output to a Qt signal so it can be streamed into the GUI's
output log while the (slow, network-bound) work happens off the GUI thread.
"""

import contextlib
import io
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from spinharmony_studio.build import setup_spinharmony


class _StreamToSignal(io.TextIOBase):
    """A writable text stream that forwards each write to a callback."""

    def __init__(self, emit) -> None:
        super().__init__()
        self._emit = emit

    def write(self, text: str) -> int:
        if text:
            self._emit(text)
        return len(text)


class SetupWorker(QThread):
    """Runs ``setup_spinharmony()`` off the GUI thread."""

    progress = pyqtSignal(str)
    succeeded = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def run(self) -> None:
        stream = _StreamToSignal(self.progress.emit)
        try:
            with contextlib.redirect_stdout(stream):
                executables: dict[str, Path] = setup_spinharmony()
        except Exception as exc:  # noqa: BLE001 - surfaced to the user, not swallowed
            self.failed.emit(str(exc))
        else:
            self.succeeded.emit(executables)
