"""Tests for :mod:`spinharmony_studio.spinvert.gui.setup_worker`."""

from unittest.mock import patch

from PyQt6.QtWidgets import QApplication

from spinharmony_studio.spinvert.gui import setup_worker as setup_worker_module
from spinharmony_studio.spinvert.gui.setup_worker import SetupWorker, _StreamToSignal

_app = QApplication.instance() or QApplication([])


def test_write_forwards_nonempty_text():
    received = []
    stream = _StreamToSignal(received.append)
    n = stream.write("hello")
    assert received == ["hello"]
    assert n == 5


def test_write_ignores_empty_text():
    received = []
    stream = _StreamToSignal(received.append)
    stream.write("")
    assert received == []


def test_success_emits_progress_and_succeeded():
    def fake_setup_spinharmony():
        print("Building spinvert...")
        return {"spinvert": "/fake/spinvert"}

    worker = SetupWorker()
    progress = []
    succeeded = []
    worker.progress.connect(progress.append)
    worker.succeeded.connect(succeeded.append)

    with patch.object(setup_worker_module, "setup_spinharmony", fake_setup_spinharmony):
        worker.run()  # call directly: exercises the same code, no thread needed

    assert any("Building spinvert" in text for text in progress)
    assert succeeded == [{"spinvert": "/fake/spinvert"}]


def test_failure_emits_failed():
    def fake_setup_spinharmony():
        raise RuntimeError("network is down")

    worker = SetupWorker()
    failed = []
    worker.failed.connect(failed.append)

    with patch.object(setup_worker_module, "setup_spinharmony", fake_setup_spinharmony):
        worker.run()

    assert failed == ["network is down"]
