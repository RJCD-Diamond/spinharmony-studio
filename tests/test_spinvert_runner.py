"""Tests for :mod:`spinharmony_studio.spinvert.gui.spinvert_runner`.

Uses real (fast, trivial) child processes rather than mocking QProcess, since
QProcess's asynchronous signal plumbing is exactly what this class wraps.
"""

import time

from PyQt6.QtWidgets import QApplication

from spinharmony_studio.spinvert.gui.spinvert_runner import SpinvertRunner

_app = QApplication.instance() or QApplication([])


def _pump_until(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while not predicate() and time.time() < deadline:
        _app.processEvents()
        time.sleep(0.01)
    assert predicate(), "condition not met before timeout"


def test_not_running_initially():
    runner = SpinvertRunner()
    assert runner.is_running() is False


def test_successful_run_emits_output_and_finished(tmp_path):
    runner = SpinvertRunner()
    received = []
    finished = []
    runner.output_received.connect(received.append)
    runner.finished.connect(finished.append)

    runner.start("/bin/echo", "hello-title", str(tmp_path))
    _pump_until(lambda: finished)

    assert finished == [0]
    assert any("hello-title" in text for text in received)


def test_is_running_true_while_process_active(tmp_path):
    runner = SpinvertRunner()
    finished = []
    runner.finished.connect(finished.append)
    runner.start("/bin/sleep", "", str(tmp_path))
    assert runner.is_running() is True
    runner.stop()
    _pump_until(lambda: finished)
    assert runner.is_running() is False


def test_stop_when_not_running_is_a_noop():
    runner = SpinvertRunner()
    runner.stop()  # must not raise


def test_failed_to_start_emits_message_and_finished(tmp_path):
    runner = SpinvertRunner(program_label="spinvert")
    received = []
    finished = []
    runner.output_received.connect(received.append)
    runner.finished.connect(finished.append)

    runner.start("/no/such/executable-xyz", "", str(tmp_path))
    _pump_until(lambda: finished)

    assert finished == [-1]
    assert any("failed to start" in text for text in received)


def test_no_stem_does_not_write_stdin(tmp_path):
    # A program with an empty title/stem should get no positional
    # argument and no stdin write attempt (exercises the "stem is None"
    # branches without needing to inspect the child's own stdin).
    runner = SpinvertRunner()
    finished = []
    runner.finished.connect(finished.append)
    runner.start("/bin/echo", "", str(tmp_path))
    _pump_until(lambda: finished)
    assert finished == [0]


def test_program_label_used_in_error_text(tmp_path):
    runner = SpinvertRunner(program_label="scatty")
    received = []
    runner.output_received.connect(received.append)
    runner.finished.connect(lambda _c: None)
    runner.start("/no/such/executable-xyz", "", str(tmp_path))
    _pump_until(lambda: received)
    assert any("scatty" in text for text in received)
