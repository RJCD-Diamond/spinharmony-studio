"""Tests for :mod:`spinharmony_studio.spinvert.gui.output_log`."""

from PyQt6.QtWidgets import QApplication

from spinharmony_studio.spinvert.gui.output_log import OutputLog

_app = QApplication.instance() or QApplication([])


def test_starts_empty():
    log = OutputLog()
    assert log.view.toPlainText() == ""


def test_append_adds_text():
    log = OutputLog()
    log.append("hello\n")
    assert log.view.toPlainText() == "hello\n"


def test_append_accumulates():
    log = OutputLog()
    log.append("line1\n")
    log.append("line2\n")
    assert log.view.toPlainText() == "line1\nline2\n"


def test_clear_empties_view():
    log = OutputLog()
    log.append("something")
    log.clear()
    assert log.view.toPlainText() == ""


def test_copy_all_selects_and_copies():
    log = OutputLog()
    log.append("copy me")
    log.copy_all()  # must not raise; exercises selectAll + copy
    clipboard = QApplication.clipboard()
    assert clipboard is not None
    assert clipboard.text() == "copy me"


def test_custom_title():
    log = OutputLog("Custom title")
    assert log.title() == "Custom title"


def test_is_read_only():
    log = OutputLog()
    assert log.view.isReadOnly() is True
