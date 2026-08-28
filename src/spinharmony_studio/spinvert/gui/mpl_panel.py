"""Reusable Qt widget: a matplotlib Figure + navigation toolbar in a vertical
layout, plus a fixed-aspect PNG export. Subclasses create their axes and add
``update_*`` methods that redraw via :meth:`refresh`."""

from pathlib import Path

from matplotlib.backends.backend_qt import NavigationToolbar2QT as NavigationToolbar
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from spinharmony_studio.spinvert.gui.plotting import DEFAULT_STYLE, PlotStyle


class MplPanel(QWidget):
    def __init__(
        self,
        *,
        style: PlotStyle | None = None,
        figsize: tuple[float, float] = (5.0, 6.0),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.plot_style = style or DEFAULT_STYLE
        self.figure = Figure(figsize=figsize)
        self.canvas = FigureCanvasQTAgg(self.figure)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(NavigationToolbar(self.canvas, self))
        layout.addWidget(self.canvas)

    def set_plot_style(self, style: PlotStyle) -> None:
        """Swap the appearance config and redraw the current data."""
        self.plot_style = style
        self.refresh()

    def refresh(self) -> None:
        """Redraw with the last data passed to ``update_*``. Subclasses
        override; the base just repaints."""
        self.canvas.draw_idle()

    def save_png(self, path: Path | str) -> None:
        """Save the current plot to a PNG at the style's fixed export size and
        dpi, independent of the on-screen panel size."""
        old_w, old_h = self.figure.get_size_inches()
        try:
            self.figure.set_size_inches(self.plot_style.export_size_inches)
            self.figure.savefig(str(path), dpi=self.plot_style.export_dpi)
        finally:
            self.figure.set_size_inches((float(old_w), float(old_h)))
            self.canvas.draw_idle()
