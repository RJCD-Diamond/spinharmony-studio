"""Reusable "blades" layout (Xbox-360 style): a horizontal ``QSplitter`` whose
left and (optional) right panes each have a thin edge :class:`BladeButton` that
shows or hides them. An optional always-visible ``center`` pane sits between
them. Whenever a blade opens or closes, the visible panes are re-shared equally
(2 panes -> 50/50, 3 panes -> thirds).
"""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QShowEvent
from PyQt6.QtWidgets import QHBoxLayout, QSplitter, QWidget

from spinharmony_studio.spinvert.gui.blade_button import BladeButton


class BladeSplitter(QWidget):
    left_toggled = pyqtSignal(bool)
    right_toggled = pyqtSignal(bool)

    def __init__(
        self,
        *,
        left: QWidget,
        left_label: str,
        center: QWidget | None = None,
        right: QWidget | None = None,
        right_label: str = "",
        left_visible: bool = True,
        right_visible: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._left = left
        self._right = right
        self._left_label = left_label
        self._right_label = right_label
        self._did_initial = False

        self.splitter = QSplitter(self)
        self.splitter.setChildrenCollapsible(True)
        # Order in the splitter: left, [center], [right].
        self._panes = [w for w in (left, center, right) if w is not None]
        for pane in self._panes:
            self.splitter.addWidget(pane)
        for i in range(self.splitter.count()):
            self.splitter.setStretchFactor(i, 1)

        self.left_blade = BladeButton(left_label, edge="left")
        self.left_blade.clicked.connect(
            lambda: self.set_left_visible(not self.left_visible)
        )

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self.left_blade)
        row.addWidget(self.splitter, stretch=1)

        self.right_blade: BladeButton | None = None
        if right is not None:
            self.right_blade = BladeButton(right_label, edge="right")
            self.right_blade.clicked.connect(
                lambda: self.set_right_visible(not self.right_visible)
            )
            row.addWidget(self.right_blade)

        left.setVisible(left_visible)
        if right is not None:
            right.setVisible(right_visible)
        self._update_blade(self.left_blade, left_visible, "left", left_label)
        if self.right_blade is not None:
            self._update_blade(self.right_blade, right_visible, "right", right_label)

    # --- public API ----------------------------------------------------

    @property
    def left_visible(self) -> bool:
        return self._left.isVisible()

    @property
    def right_visible(self) -> bool:
        return self._right is not None and self._right.isVisible()

    def set_left_visible(self, visible: bool) -> None:
        self._left.setVisible(visible)
        self._rebalance()
        self._update_blade(self.left_blade, visible, "left", self._left_label)
        self.left_toggled.emit(visible)

    def set_right_visible(self, visible: bool) -> None:
        if self._right is None or self.right_blade is None:
            return
        self._right.setVisible(visible)
        self._rebalance()
        self._update_blade(self.right_blade, visible, "right", self._right_label)
        self.right_toggled.emit(visible)

    # --- internals ---------------------------------------------------

    @staticmethod
    def _update_blade(blade: BladeButton, visible: bool, side: str, label: str) -> None:
        if side == "left":
            blade.set_arrow("◀" if visible else "▶")
        else:
            blade.set_arrow("▶" if visible else "◀")
        blade.setToolTip(
            f"Collapse the {label.lower()} panel"
            if visible
            else f"Show the {label.lower()} panel"
        )

    def _rebalance(self) -> None:
        visible = [i for i, pane in enumerate(self._panes) if pane.isVisible()]
        if not visible:
            return
        total = self.splitter.width()
        if total <= 0:
            total = sum(self.splitter.sizes()) or 1000
        each = total // len(visible)
        sizes = [0] * len(self._panes)
        for i in visible:
            sizes[i] = each
        sizes[visible[-1]] += total - each * len(visible)  # absorb rounding
        self.splitter.setSizes(sizes)

    def showEvent(self, a0: QShowEvent | None) -> None:  # noqa: N802 (Qt override)
        super().showEvent(a0)
        if not self._did_initial:
            self._did_initial = True
            self._rebalance()
