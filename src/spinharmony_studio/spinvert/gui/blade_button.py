"""A thin vertical "blade" toggle button (Xbox-360 style): a direction arrow at
the top and the section's name printed vertically down the strip, so it is
obvious which panel a click will reveal or hide."""

from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QPainter, QPaintEvent, QPalette
from PyQt6.QtWidgets import QSizePolicy, QToolButton, QWidget


class BladeButton(QToolButton):
    def __init__(
        self,
        label: str,
        *,
        edge: str = "left",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._label = label
        self._edge = edge  # "left" -> text reads up; "right" -> text reads down
        self._arrow = "◀"  # ◀

        self.setAutoRaise(True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setFixedWidth(self.fontMetrics().height() + 12)
        self.setMinimumHeight(140)

    def set_arrow(self, arrow: str) -> None:
        self._arrow = arrow
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt override)
        text_len = self.fontMetrics().horizontalAdvance(self._label)
        return QSize(self.width(), self.width() + text_len + 24)

    def paintEvent(self, a0: QPaintEvent | None) -> None:  # noqa: N802 (Qt override)
        super().paintEvent(a0)  # frame / hover / pressed background

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setPen(self.palette().color(QPalette.ColorRole.ButtonText))

        width = self.width()
        height = self.height()

        # Arrow: horizontal, in a square box at the top.
        painter.drawText(
            QRectF(0, 2, width, width),
            int(Qt.AlignmentFlag.AlignCenter),
            self._arrow,
        )

        # Label: rotated to run along the strip.
        label_top = width + 4
        painter.save()
        painter.translate(width / 2, (label_top + height) / 2)
        painter.rotate(-90 if self._edge == "left" else 90)
        span = max(1.0, height - label_top - 4)
        painter.drawText(
            QRectF(-span / 2, -width / 2, span, width),
            int(Qt.AlignmentFlag.AlignCenter),
            self._label,
        )
        painter.restore()
        painter.end()
