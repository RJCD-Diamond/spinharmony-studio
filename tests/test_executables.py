"""Tests for :mod:`spinharmony_studio.spinvert.gui.executables`."""

import os
import shutil
import stat
from unittest.mock import MagicMock, patch

from PyQt6.QtWidgets import QApplication, QMessageBox

from spinharmony_studio.spinvert.gui.executables import (
    diagnose_executable,
    prepare_executable,
    resolve_executable,
)

# A QApplication is required to construct any QWidget/QMessageBox on some
# platforms even headlessly; ensure one exists for this module's tests.
_app = QApplication.instance() or QApplication([])


def _make_exe(tmp_path, header: bytes, name="prog", executable=True):
    path = tmp_path / name
    path.write_bytes(header + b"\x00" * 100)
    if executable:
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def test_resolves_existing_file_path(tmp_path):
    path = tmp_path / "prog"
    path.write_text("")
    assert resolve_executable(str(path)) == str(path)


def test_resolves_bare_name_on_path():
    assert resolve_executable("ls") == shutil.which("ls")


def test_returns_none_when_not_found():
    assert resolve_executable("no-such-program-xyz") is None


def test_expands_user_home(tmp_path):
    (tmp_path / "prog").write_text("")
    with patch.dict(os.environ, {"HOME": str(tmp_path)}):
        assert resolve_executable("~/prog") == str(tmp_path / "prog")


def test_missing_path_reports_cannot_read(tmp_path):
    problem = diagnose_executable(str(tmp_path / "nope"))
    assert problem is not None
    assert "Cannot read" in problem


def test_directory_is_not_a_regular_file(tmp_path):
    problem = diagnose_executable(str(tmp_path))
    assert problem is not None
    assert "not a regular file" in problem


def test_not_executable_suggests_chmod(tmp_path):
    path = _make_exe(tmp_path, b"\x7fELF", executable=False)
    problem = diagnose_executable(str(path))
    assert problem is not None
    assert "chmod +x" in problem


def test_empty_file(tmp_path):
    path = tmp_path / "empty"
    path.write_bytes(b"")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    problem = diagnose_executable(str(path))
    assert problem is not None
    assert "empty" in problem


def test_windows_exe_reported(tmp_path):
    path = _make_exe(tmp_path, b"MZ")
    problem = diagnose_executable(str(path))
    assert problem is not None
    assert "Windows executable" in problem


def test_elf_matching_host_arch_is_none(tmp_path):
    head = b"\x7fELF" + b"\x00" * 14 + (0x3E).to_bytes(2, "little")
    path = _make_exe(tmp_path, head)
    with patch("platform.machine", return_value="x86_64"):
        assert diagnose_executable(str(path)) is None


def test_elf_mismatched_arch_reported(tmp_path):
    head = b"\x7fELF" + b"\x00" * 14 + (0xB7).to_bytes(2, "little")  # AArch64
    path = _make_exe(tmp_path, head)
    with patch("platform.machine", return_value="x86_64"):
        problem = diagnose_executable(str(path))
        assert problem is not None
    assert "AArch64" in problem and "x86_64" in problem


def test_elf_unknown_host_arch_not_flagged(tmp_path):
    head = b"\x7fELF" + b"\x00" * 14 + (0x3E).to_bytes(2, "little")
    path = _make_exe(tmp_path, head)
    with patch("platform.machine", return_value="some-weird-arch"):
        assert diagnose_executable(str(path)) is None


def test_macho_matching_host_arch_is_none(tmp_path):
    head = b"\xcf\xfa\xed\xfe" + (0x01000007).to_bytes(4, "little")
    path = _make_exe(tmp_path, head)
    with patch("platform.machine", return_value="x86_64"):
        assert diagnose_executable(str(path)) is None


def test_macho_mismatched_arch_reported(tmp_path):
    head = b"\xcf\xfa\xed\xfe" + (0x0100000C).to_bytes(4, "little")  # AArch64
    path = _make_exe(tmp_path, head)
    with patch("platform.machine", return_value="x86_64"):
        problem = diagnose_executable(str(path))
        assert problem is not None
    assert "macOS binary" in problem


def test_macho_universal_never_flagged(tmp_path):
    head = b"\xca\xfe\xba\xbe" + b"\x00" * 4
    path = _make_exe(tmp_path, head)
    with patch("platform.machine", return_value="arm64"):
        assert diagnose_executable(str(path)) is None


def test_shebang_with_available_interpreter_is_none(tmp_path):
    path = _make_exe(tmp_path, b"#!/bin/sh\necho hi\n")
    assert diagnose_executable(str(path)) is None


def test_shebang_with_missing_interpreter_reported(tmp_path):
    path = _make_exe(tmp_path, b"#!/no/such/interpreter-xyz\n")
    problem = diagnose_executable(str(path))
    assert problem is not None
    assert "interpreter" in problem


def test_text_file_reported(tmp_path):
    path = tmp_path / "script.txt"
    path.write_text("just plain text content here\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    problem = diagnose_executable(str(path))
    assert problem is not None
    assert "text file" in problem


def test_unrecognised_binary_garbage_reported(tmp_path):
    path = _make_exe(tmp_path, bytes(range(200, 220)))
    problem = diagnose_executable(str(path))
    assert problem is not None
    assert "not a recognised executable format" in problem


def test_empty_path_warns_and_returns_none():
    with patch.object(QMessageBox, "warning") as mock_warn:
        result = prepare_executable(None, "  ", "spinvert", lambda _t: None)
    assert result is None
    assert mock_warn.called


def test_unresolvable_path_warns_and_returns_none():
    with patch.object(QMessageBox, "warning") as mock_warn:
        result = prepare_executable(
            None, "no-such-program-xyz", "spinvert", lambda _t: None
        )
    assert result is None
    assert mock_warn.called


def test_diagnosed_problem_logs_and_warns(tmp_path):
    path = tmp_path / "script.txt"
    path.write_text("plain text\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    log = MagicMock()
    with patch.object(QMessageBox, "warning") as mock_warn:
        result = prepare_executable(None, str(path), "spinvert", log)
    assert result is None
    assert log.called
    assert mock_warn.called


def test_valid_executable_returns_resolved_path(tmp_path):
    path = _make_exe(tmp_path, b"#!/bin/sh\n")
    result = prepare_executable(None, str(path), "spinvert", lambda _t: None)
    assert result == str(path)
