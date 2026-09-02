"""Shared 'save your changes?' prompt used before running an external program.

If the configuration built from the form differs from the file on disk (or the
file does not exist yet), the user is asked whether to save it first.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from PyQt6.QtWidgets import QMessageBox, QWidget


class _WritableConfig(Protocol):
    def to_text(self) -> str: ...
    def save_to_file(self, path: str | Path) -> object: ...


def confirm_save_before_run(
    parent: QWidget,
    config: _WritableConfig,
    path: Path,
    loader: Callable[[Path], _WritableConfig],
    program: str,
    log: Callable[[str], None],
) -> bool:
    """Return True if the run should proceed, False if the user cancelled.

    ``loader(path)`` re-parses the on-disk config for comparison. When the form
    and file already match, this returns True with no dialog.
    """
    file_exists = path.exists()
    if file_exists:
        try:
            if loader(path).to_text() == config.to_text():
                return True
        except Exception:
            pass  # unreadable / stale -> treat as "differs"

    if file_exists:
        buttons = (
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel
        )
        text = (
            f"The configuration in the form differs from {path.name}.\n\n"
            f"Save your changes before running {program}?\n"
            "(No runs the last saved version.)"
        )
    else:
        buttons = QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
        text = (
            f"{path.name} has not been saved yet.\n\n"
            f"Save the configuration before running {program}?"
        )

    reply = QMessageBox.question(
        parent,
        "Save configuration?",
        text,
        buttons,
        QMessageBox.StandardButton.Yes,
    )
    if reply == QMessageBox.StandardButton.Cancel:
        return False
    if reply == QMessageBox.StandardButton.Yes:
        config.save_to_file(path)
        log(f"Wrote {path}\n")
    return True
