"""Tests for :mod:`spinharmony_studio.spinvert.gui.config_prompt`."""

from unittest.mock import MagicMock, patch

from PyQt6.QtWidgets import QApplication, QMessageBox

from spinharmony_studio.spinvert.gui.config_prompt import confirm_save_before_run

_app = QApplication.instance() or QApplication([])


class _FakeConfig:
    def __init__(self, text: str):
        self._text = text
        self.saved_to = None

    def to_text(self) -> str:
        return self._text

    def save_to_file(self, path):
        self.saved_to = path
        return path


def _loader_returning(text):
    return lambda path: _FakeConfig(text)


def test_matching_file_proceeds_without_dialog(tmp_path):
    path = tmp_path / "Foo_config.txt"
    path.write_text("same")
    config = _FakeConfig("same")
    log = MagicMock()
    with patch.object(QMessageBox, "question") as mock_question:
        result = confirm_save_before_run(
            None, config, path, _loader_returning("same"), "spinvert", log
        )
    assert result is True
    assert not mock_question.called
    assert config.saved_to is None


def test_unreadable_existing_file_treated_as_differing(tmp_path):
    path = tmp_path / "Foo_config.txt"
    path.write_text("garbage")

    def bad_loader(_path):
        raise ValueError("cannot parse")

    config = _FakeConfig("new text")
    with patch.object(
        QMessageBox, "question", return_value=QMessageBox.StandardButton.No
    ) as mock_question:
        result = confirm_save_before_run(
            None, config, path, bad_loader, "spinvert", MagicMock()
        )
    assert result is True
    assert mock_question.called


def test_differing_file_yes_saves_and_logs(tmp_path):
    path = tmp_path / "Foo_config.txt"
    path.write_text("old")
    config = _FakeConfig("new")
    log = MagicMock()
    with patch.object(
        QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes
    ):
        result = confirm_save_before_run(
            None, config, path, _loader_returning("old"), "spinvert", log
        )
    assert result is True
    assert config.saved_to == path
    assert log.called


def test_differing_file_no_proceeds_without_saving(tmp_path):
    path = tmp_path / "Foo_config.txt"
    path.write_text("old")
    config = _FakeConfig("new")
    with patch.object(
        QMessageBox, "question", return_value=QMessageBox.StandardButton.No
    ):
        result = confirm_save_before_run(
            None, config, path, _loader_returning("old"), "spinvert", MagicMock()
        )
    assert result is True
    assert config.saved_to is None


def test_differing_file_cancel_aborts(tmp_path):
    path = tmp_path / "Foo_config.txt"
    path.write_text("old")
    config = _FakeConfig("new")
    with patch.object(
        QMessageBox, "question", return_value=QMessageBox.StandardButton.Cancel
    ):
        result = confirm_save_before_run(
            None, config, path, _loader_returning("old"), "spinvert", MagicMock()
        )
    assert result is False
    assert config.saved_to is None


def test_missing_file_yes_saves(tmp_path):
    path = tmp_path / "Foo_config.txt"
    config = _FakeConfig("new")
    log = MagicMock()
    with patch.object(
        QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes
    ):
        result = confirm_save_before_run(
            None, config, path, _loader_returning("irrelevant"), "spinvert", log
        )
    assert result is True
    assert config.saved_to == path


def test_missing_file_cancel_aborts(tmp_path):
    path = tmp_path / "Foo_config.txt"
    config = _FakeConfig("new")
    with patch.object(
        QMessageBox, "question", return_value=QMessageBox.StandardButton.Cancel
    ):
        result = confirm_save_before_run(
            None,
            config,
            path,
            _loader_returning("irrelevant"),
            "spinvert",
            MagicMock(),
        )
    assert result is False
