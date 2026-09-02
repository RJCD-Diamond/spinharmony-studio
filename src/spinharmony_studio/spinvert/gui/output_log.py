"""Reusable read-only program-output pane: a monospaced, non-wrapping text view
in a group box, with faithful streaming (keeps the view pinned to the bottom
unless the user has scrolled up)."""

from PyQt6.QtGui import QFontDatabase, QTextCursor
from PyQt6.QtWidgets import QGroupBox, QPlainTextEdit, QVBoxLayout, QWidget


class OutputLog(QGroupBox):
    def __init__(
        self, title: str = "Program output", parent: QWidget | None = None
    ) -> None:
        super().__init__(title, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(20000)
        self.view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.view.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        # Small floor so a splitter handle above/below stays grabbable.
        self.view.setMinimumHeight(60)
        layout.addWidget(self.view)

    def append(self, text: str) -> None:
        """Append raw text, preserving its own line breaks and keeping the view
        scrolled to the bottom unless the user has scrolled up."""
        scrollbar = self.view.verticalScrollBar()
        at_bottom = scrollbar is None or scrollbar.value() >= scrollbar.maximum() - 4

        cursor = self.view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)

        if at_bottom and scrollbar is not None:
            scrollbar.setValue(scrollbar.maximum())

    def copy_all(self) -> None:
        self.view.selectAll()
        self.view.copy()

    def clear(self) -> None:
        self.view.clear()
