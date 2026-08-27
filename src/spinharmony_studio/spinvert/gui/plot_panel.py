"""Matplotlib panel showing data vs. current fit and the data-minus-fit
difference."""

import numpy as np
from matplotlib.backends.backend_qt import NavigationToolbar2QT as NavigationToolbar
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtWidgets import QVBoxLayout, QWidget


class PlotPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        figure = Figure(figsize=(5, 7))
        self.canvas = FigureCanvasQTAgg(figure)
        self.ax_data, self.ax_diff = figure.subplots(
            2, 1, height_ratios=[3, 1], gridspec_kw={"hspace": 0.4}
        )
        self.ax_diff.sharex(self.ax_data)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(NavigationToolbar(self.canvas, self))
        layout.addWidget(self.canvas)

        self._init_axes()

    def _init_axes(self) -> None:
        self.ax_data.set_xlabel("Q")
        self.ax_data.set_ylabel("Intensity")
        self.ax_diff.set_xlabel("Q")
        self.ax_diff.set_ylabel("Data - fit")

    def update_data_and_fit(
        self,
        data: tuple[np.ndarray, np.ndarray, np.ndarray] | None,
        fit: tuple[np.ndarray, np.ndarray, np.ndarray] | None,
        fit_label: str | None,
    ) -> None:
        self.ax_data.clear()
        if data is not None and data[0].size:
            q, intensity, error = data
            self.ax_data.errorbar(
                q,
                intensity,
                yerr=error,
                fmt="o",
                ms=3,
                color="0.4",
                ecolor="0.75",
                elinewidth=1,
                label="Data",
            )
        if fit is not None and fit[0].size:
            fit_q, fit_intensity, _ = fit
            self.ax_data.plot(
                fit_q,
                fit_intensity,
                "-",
                color="crimson",
                label=fit_label or "Fit",
            )
        self.ax_data.set_xlabel("Q")
        self.ax_data.set_ylabel("Intensity")
        if data is not None or fit is not None:
            self.ax_data.legend(loc="best")

        self._update_difference(data, fit)
        self.canvas.draw_idle()

    def _update_difference(
        self,
        data: tuple[np.ndarray, np.ndarray, np.ndarray] | None,
        fit: tuple[np.ndarray, np.ndarray, np.ndarray] | None,
    ) -> None:
        self.ax_diff.clear()
        self.ax_diff.set_xlabel("Q")
        self.ax_diff.set_ylabel("Data - fit")

        if data is None or fit is None or not data[0].size or not fit[0].size:
            return

        q, intensity, error = data
        fit_q, fit_intensity, _ = fit

        # The fit is generally sampled on the same Q grid as the data, but
        # interpolate to be safe and only compare over the fit's Q range.
        in_range = (q >= fit_q.min()) & (q <= fit_q.max())
        if not in_range.any():
            return
        q = q[in_range]
        residual = intensity[in_range] - np.interp(q, fit_q, fit_intensity)
        err = error[in_range] if error is not None and error.size else None

        self.ax_diff.axhline(0.0, color="0.6", lw=1)
        self.ax_diff.errorbar(
            q,
            residual,
            yerr=err,
            fmt="-",
            color="seagreen",
            ecolor="0.8",
            elinewidth=1,
            label="Data - fit",
        )
        self.ax_diff.legend(loc="best")
