"""Tests for :mod:`spinharmony_studio.spinvert.gui.blade_splitter`."""

from PyQt6.QtWidgets import QApplication, QLabel

from spinharmony_studio.spinvert.gui.blade_splitter import BladeSplitter

_app = QApplication.instance() or QApplication([])


def _splitter(**overrides):
    # isVisible() reflects the real Qt show/hide state, which requires the
    # whole widget tree (not just this widget) to actually be shown - a
    # freshly constructed, never-shown widget reports isVisible()=False
    # regardless of setVisible(True), so every test needs a real .show().
    kwargs = {
        "left": QLabel("left"),
        "left_label": "Configuration",
        "center": QLabel("center"),
        "right": QLabel("right"),
        "right_label": "Plot",
        "left_visible": True,
        "right_visible": True,
    }
    kwargs.update(overrides)
    splitter = BladeSplitter(**kwargs)
    splitter.show()
    return splitter


def test_two_pane_layout_has_no_right_blade():
    splitter = BladeSplitter(left=QLabel("left"), left_label="Configuration")
    assert splitter.right_blade is None


def test_three_pane_layout_has_right_blade():
    splitter = _splitter()
    assert splitter.right_blade is not None


def test_initial_visibility_respected():
    splitter = _splitter(left_visible=False, right_visible=False)
    assert splitter.left_visible is False
    assert splitter.right_visible is False


def test_default_visibility_is_true():
    splitter = _splitter()
    assert splitter.left_visible is True
    assert splitter.right_visible is True


def test_set_left_visible_updates_state_and_emits():
    splitter = _splitter()
    received = []
    splitter.left_toggled.connect(received.append)
    splitter.set_left_visible(False)
    assert splitter.left_visible is False
    assert received == [False]


def test_set_right_visible_updates_state_and_emits():
    splitter = _splitter()
    received = []
    splitter.right_toggled.connect(received.append)
    splitter.set_right_visible(False)
    assert splitter.right_visible is False
    assert received == [False]


def test_set_right_visible_noop_without_right_pane():
    splitter = BladeSplitter(left=QLabel("left"), left_label="Configuration")
    received = []
    splitter.right_toggled.connect(received.append)
    splitter.set_right_visible(True)  # must not raise
    assert received == []


def test_left_blade_click_toggles_visibility():
    splitter = _splitter(left_visible=True)
    splitter.left_blade.click()
    assert splitter.left_visible is False


def test_right_blade_click_toggles_visibility():
    splitter = _splitter(right_visible=True)
    assert splitter.right_blade is not None
    splitter.right_blade.click()
    assert splitter.right_visible is False


def test_blade_arrow_and_tooltip_update_on_toggle():
    splitter = _splitter(left_visible=True)
    assert splitter.left_blade._arrow == "◀"
    splitter.set_left_visible(False)
    assert splitter.left_blade._arrow == "▶"
    assert "Show" in splitter.left_blade.toolTip()


def test_right_blade_arrow_updates_on_toggle():
    splitter = _splitter(right_visible=True)
    assert splitter.right_blade is not None
    assert splitter.right_blade._arrow == "▶"
    splitter.set_right_visible(False)
    assert splitter.right_blade._arrow == "◀"


def test_rebalance_with_no_visible_panes_does_not_raise():
    splitter = _splitter(left_visible=False, right_visible=False)
    splitter._left.setVisible(False)
    splitter._panes[1].setVisible(False)
    splitter._rebalance()  # all panes hidden -> early return, no crash


def test_show_event_rebalances_once():
    splitter = _splitter()
    splitter.resize(900, 600)
    splitter.show()
    assert splitter._did_initial is True
    # A second show should not re-trigger the "initial" rebalance flag reset.
    splitter.show()
    assert splitter._did_initial is True
