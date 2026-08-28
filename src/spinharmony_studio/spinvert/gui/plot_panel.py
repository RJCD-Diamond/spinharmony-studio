"""On-screen panel: data vs. current fit, and the data-minus-fit difference.

The drawing itself lives in ``plotting.draw_data_and_fit`` so it is reusable and
styleable; this class only owns the Qt widget and the last-drawn state.
"""

from spinharmony_studio.spinvert.gui.mpl_panel import MplPanel
from spinharmony_studio.spinvert.gui.plotting import (
    DataTriple,
    FitPair,
    PlotStyle,
    draw_data_and_fit,
)


class PlotPanel(MplPanel):
    def __init__(self, *, style: PlotStyle | None = None, parent=None) -> None:
        super().__init__(style=style, figsize=(5, 7), parent=parent)
        self.ax_data, self.ax_diff = self.figure.subplots(
            2, 1, height_ratios=[3, 1], gridspec_kw={"hspace": 0.4}
        )
        self.ax_diff.sharex(self.ax_data)

        self._data: DataTriple | None = None
        self._fit: FitPair | None = None
        self._fit_label: str | None = None
        self.refresh()

    def update_data_and_fit(
        self,
        data: DataTriple | None,
        fit: FitPair | None,
        fit_label: str | None = None,
    ) -> None:
        self._data, self._fit, self._fit_label = data, fit, fit_label
        self.refresh()

    def refresh(self) -> None:
        draw_data_and_fit(
            self.ax_data,
            self.ax_diff,
            self._data,
            self._fit,
            style=self.plot_style,
            fit_label=self._fit_label,
        )
        self.canvas.draw_idle()
