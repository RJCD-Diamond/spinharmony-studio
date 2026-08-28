"""On-screen panel: the spincorrel spin-correlation function
([title]_scf.txt), <S_i.S_j> versus radial distance.

The drawing itself lives in ``plotting.draw_correlation`` so it is reusable and
styleable; this class only owns the Qt widget and the last-drawn state.
"""

from spinharmony_studio.spinvert.gui.mpl_panel import MplPanel
from spinharmony_studio.spinvert.gui.plotting import (
    DataTriple,
    PlotStyle,
    draw_correlation,
)


class CorrelPanel(MplPanel):
    def __init__(self, *, style: PlotStyle | None = None, parent=None) -> None:
        super().__init__(style=style, figsize=(4, 5), parent=parent)
        self.ax = self.figure.subplots()

        self._scf: DataTriple | None = None
        self._label: str | None = None
        self.refresh()

    def update_scf(self, scf: DataTriple | None, label: str | None = None) -> None:
        self._scf, self._label = scf, label
        self.refresh()

    def refresh(self) -> None:
        draw_correlation(self.ax, self._scf, style=self.plot_style, label=self._label)
        self.canvas.draw_idle()
