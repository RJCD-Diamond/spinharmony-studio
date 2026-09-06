"""Tests for :mod:`spinharmony_studio.spinvert.gui.blade_button`."""

from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication

from spinharmony_studio.spinvert.gui.blade_button import BladeButton

_app = QApplication.instance() or QApplication([])


def test_default_edge_is_left():
    button = BladeButton("Configuration")
    assert button._edge == "left"
    assert button._label == "Configuration"


def test_explicit_edge():
    button = BladeButton("Plot", edge="right")
    assert button._edge == "right"


def test_set_arrow_updates_state():
    button = BladeButton("Configuration")
    button.set_arrow("▶")
    assert button._arrow == "▶"


def test_size_hint_reflects_label_length():
    short = BladeButton("A")
    long = BladeButton("A much longer label")
    assert long.sizeHint().height() > short.sizeHint().height()


def test_paints_without_error_left_edge():
    button = BladeButton("Configuration", edge="left")
    button.resize(30, 200)
    pixmap = QPixmap(30, 200)
    button.render(pixmap)  # exercises paintEvent


def test_paints_without_error_right_edge():
    button = BladeButton("Spin correlation", edge="right")
    button.resize(30, 200)
    pixmap = QPixmap(30, 200)
    button.render(pixmap)
