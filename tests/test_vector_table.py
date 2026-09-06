"""Tests for :mod:`spinharmony_studio.spinvert.gui.vector_table`."""

from PyQt6.QtWidgets import QApplication

from spinharmony_studio.spinvert.gui.vector_table import Vector3Table

_app = QApplication.instance() or QApplication([])


def test_starts_empty():
    table = Vector3Table()
    assert table.row_count() == 0
    assert table.vectors() == []


def test_add_row_default():
    table = Vector3Table()
    table.add_row()
    assert table.row_count() == 1
    assert table.vectors() == [(0.0, 0.0, 0.0)]


def test_add_row_with_values():
    table = Vector3Table()
    table.add_row((1.0, 2.0, 3.0))
    assert table.vectors() == [(1.0, 2.0, 3.0)]


def test_add_row_emits_signal():
    table = Vector3Table()
    received = []
    table.rows_changed.connect(lambda: received.append(True))
    table.add_row()
    assert received == [True]


def test_set_vectors_replaces_rows():
    table = Vector3Table()
    table.add_row((9.0, 9.0, 9.0))
    table.set_vectors([(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)])
    assert table.vectors() == [(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)]


def test_set_row_count_grows():
    table = Vector3Table()
    table.set_row_count(3)
    assert table.row_count() == 3


def test_set_row_count_shrinks_and_emits():
    table = Vector3Table()
    table.set_vectors([(1, 1, 1), (2, 2, 2), (3, 3, 3)])
    received = []
    table.rows_changed.connect(lambda: received.append(True))
    table.set_row_count(1)
    assert table.row_count() == 1
    assert received == [True]


def test_set_row_count_same_is_noop():
    table = Vector3Table()
    table.set_row_count(2)
    received = []
    table.rows_changed.connect(lambda: received.append(True))
    table.set_row_count(2)
    assert received == []


def test_remove_selected_removes_selected_rows():
    table = Vector3Table()
    table.set_vectors([(1, 1, 1), (2, 2, 2), (3, 3, 3)])
    table.table.selectRow(1)
    table._remove_selected()
    assert table.row_count() == 2
    assert table.vectors() == [(1.0, 1.0, 1.0), (3.0, 3.0, 3.0)]


def test_remove_selected_with_no_selection_is_noop():
    table = Vector3Table()
    table.add_row()
    table.table.clearSelection()
    received = []
    table.rows_changed.connect(lambda: received.append(True))
    table._remove_selected()
    assert table.row_count() == 1
    assert received == []


def test_custom_headers():
    table = Vector3Table(("a", "b", "c"))
    header = table.table.horizontalHeaderItem(0)
    assert header is not None
    assert header.text() == "a"
