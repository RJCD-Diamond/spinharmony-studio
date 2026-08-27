"""A small editable table of 3-vectors, used for SITE and ANISOTROPY."""

from collections.abc import Sequence

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from spinharmony_studio.spinvert.config import Vector3


class Vector3Table(QWidget):
    """Editable list of (x, y, z) rows, e.g. fractional coordinates."""

    rows_changed = pyqtSignal()

    def __init__(
        self,
        headers: Sequence[str] = ("x", "y", "z"),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.table = QTableWidget(0, 3, self)
        self.table.setHorizontalHeaderLabels(list(headers))
        header = self.table.horizontalHeader()
        assert header is not None
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        # Leave room for several rows: multiple sites are the common case.
        self.table.setMinimumHeight(200)

        add_button = QPushButton("Add row")
        remove_button = QPushButton("Remove selected")
        add_button.clicked.connect(lambda: self.add_row())
        remove_button.clicked.connect(self._remove_selected)

        button_row = QHBoxLayout()
        button_row.addWidget(add_button)
        button_row.addWidget(remove_button)
        button_row.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.table)
        layout.addLayout(button_row)

    def add_row(self, vector: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        for col, value in enumerate(vector):
            box = QDoubleSpinBox()
            box.setRange(-1e6, 1e6)
            box.setDecimals(6)
            box.setValue(value)
            self.table.setCellWidget(row, col, box)
        self.rows_changed.emit()

    def _remove_selected(self) -> None:
        selected_rows = {index.row() for index in self.table.selectedIndexes()}
        rows = sorted(selected_rows, reverse=True)
        for row in rows:
            self.table.removeRow(row)
        if rows:
            self.rows_changed.emit()

    def set_row_count(self, count: int) -> None:
        current = self.table.rowCount()
        if count > current:
            for _ in range(count - current):
                self.add_row()
        elif count < current:
            for row in reversed(range(count, current)):
                self.table.removeRow(row)
            self.rows_changed.emit()

    def vectors(self) -> list[Vector3]:
        result = []
        for row in range(self.table.rowCount()):
            values = []
            for col in range(3):
                widget = self.table.cellWidget(row, col)
                assert isinstance(widget, QDoubleSpinBox)
                values.append(widget.value())
            result.append((values[0], values[1], values[2]))
        return result

    def set_vectors(self, vectors: Sequence[Sequence[float]]) -> None:
        self.table.setRowCount(0)
        for vector in vectors:
            self.add_row((vector[0], vector[1], vector[2]))

    def row_count(self) -> int:
        return self.table.rowCount()
