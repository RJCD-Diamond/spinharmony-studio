"""Widget for editing all the fields of a SpinvertConfig."""

from typing import Literal

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from spinharmony_studio.spinvert.config import (
    CellParameters,
    FormFactorCoefficients,
    RefineOrFloat,
    SpinvertConfig,
)
from spinharmony_studio.spinvert.gui.ion_panel import IonPanel
from spinharmony_studio.spinvert.gui.vector_table import Vector3Table

_SPIN_DIMENSION_OPTIONS = ["1 - Ising", "2 - XY", "3 - Heisenberg"]
_BACKGROUND_TYPES = ["None", "Flat background", "Linear background"]
_REFINE_OR_FIXED = ["REFINE", "Fixed value"]


class ConfigFormWidget(QWidget):
    """Edits every SpinvertConfig field except TITLE (owned by MainWindow,
    since it also drives which data/output files are read)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)

        layout.addWidget(self._build_cell_group())
        layout.addWidget(self._build_sites_group())
        layout.addWidget(self._build_spin_group())
        layout.addWidget(self._build_ion_group())
        layout.addWidget(self._build_refinement_group())
        layout.addWidget(self._build_scale_and_background_group())
        layout.addStretch()

    # --- construction helpers -------------------------------------------------

    def _build_cell_group(self) -> QGroupBox:
        group = QGroupBox("Cell")
        form = QFormLayout(group)

        self.cell_a = QDoubleSpinBox()
        self.cell_b = QDoubleSpinBox()
        self.cell_c = QDoubleSpinBox()
        for box in (self.cell_a, self.cell_b, self.cell_c):
            box.setRange(0.001, 1000)
            box.setDecimals(6)
            box.setValue(1.0)

        self.cell_alpha = QDoubleSpinBox()
        self.cell_beta = QDoubleSpinBox()
        self.cell_gamma = QDoubleSpinBox()
        for box in (self.cell_alpha, self.cell_beta, self.cell_gamma):
            box.setRange(0.001, 179.999)
            box.setDecimals(4)
            box.setValue(90.0)

        form.addRow(
            "Lengths (a, b, c)",
            self._labelled_row(
                ("a", self.cell_a), ("b", self.cell_b), ("c", self.cell_c)
            ),
        )
        form.addRow(
            "Angles (alpha, beta, gamma)",
            self._labelled_row(
                ("alpha", self.cell_alpha),
                ("beta", self.cell_beta),
                ("gamma", self.cell_gamma),
            ),
        )
        return group

    @staticmethod
    def _labelled_row(*labelled_boxes: tuple[str, QWidget]) -> QWidget:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        for label, box in labelled_boxes:
            row.addWidget(QLabel(label))
            row.addWidget(box)
        row.addStretch()
        widget = QWidget()
        widget.setLayout(row)
        return widget

    def _build_sites_group(self) -> QGroupBox:
        group = QGroupBox("Sites (fractional coordinates)")
        layout = QVBoxLayout(group)
        self.sites_table = Vector3Table(("x", "y", "z"))
        self.sites_table.add_row((0.0, 0.0, 0.0))
        self.sites_table.rows_changed.connect(self._sync_anisotropy_rows)
        layout.addWidget(self.sites_table)
        return group

    def _build_spin_group(self) -> QGroupBox:
        group = QGroupBox("Spin dimension / anisotropy")
        layout = QVBoxLayout(group)

        self.spin_dimension_combo = QComboBox()
        self.spin_dimension_combo.addItems(_SPIN_DIMENSION_OPTIONS)
        self.spin_dimension_combo.setCurrentIndex(2)  # Heisenberg
        self.spin_dimension_combo.currentIndexChanged.connect(
            self._on_spin_dimension_changed
        )

        self.anisotropy_table = Vector3Table(("x", "y", "z"))

        layout.addWidget(QLabel("SPIN_DIMENSION"))
        layout.addWidget(self.spin_dimension_combo)
        layout.addWidget(
            QLabel("ANISOTROPY (one vector per site, required for Ising/XY)")
        )
        layout.addWidget(self.anisotropy_table)

        self._on_spin_dimension_changed()
        return group

    def _build_ion_group(self) -> QGroupBox:
        # The j0/j2 coefficients and C2 are not edited by hand: they follow the
        # magnetic ion (and its "orbital moment quenched" checkbox) in IonPanel.
        self._j0_coefficients: FormFactorCoefficients | None = None
        self._j2_coefficients: FormFactorCoefficients | None = None
        self._c2: float = 0.0

        self.ion_panel = IonPanel()
        self.ion_panel.ion_changed.connect(self._on_ion_changed)
        self.ion_panel.apply_scale_requested.connect(self._set_scale_from_ion)

        self._on_ion_changed()
        return self.ion_panel

    def _build_refinement_group(self) -> QGroupBox:
        group = QGroupBox("Refinement")
        form = QFormLayout(group)

        self.weight_box = QDoubleSpinBox()
        self.weight_box.setRange(1e-9, 1e6)
        self.weight_box.setDecimals(6)
        self.weight_box.setValue(1.0)

        self.moves_box = QSpinBox()
        self.moves_box.setRange(1, 1_000_000_000)
        self.moves_box.setValue(300)

        self.box_x = QSpinBox()
        self.box_y = QSpinBox()
        self.box_z = QSpinBox()
        for box in (self.box_x, self.box_y, self.box_z):
            box.setRange(1, 1000)
            box.setValue(5)
        box_row = QHBoxLayout()
        box_row.addWidget(self.box_x)
        box_row.addWidget(self.box_y)
        box_row.addWidget(self.box_z)
        box_row_widget = QWidget()
        box_row_widget.setLayout(box_row)

        self.runs_box = QSpinBox()
        self.runs_box.setRange(1, 1_000_000)
        self.runs_box.setValue(1)

        form.addRow("WEIGHT", self.weight_box)
        form.addRow("MOVES", self.moves_box)
        form.addRow("BOX (nx, ny, nz)", box_row_widget)
        form.addRow("RUNS", self.runs_box)
        return group

    def _build_scale_and_background_group(self) -> QGroupBox:
        group = QGroupBox("Scale / background / data")
        form = QFormLayout(group)

        self.scale_mode_combo = QComboBox()
        self.scale_mode_combo.addItems(_REFINE_OR_FIXED)
        self.scale_value_box = QDoubleSpinBox()
        self.scale_value_box.setRange(-1e9, 1e9)
        self.scale_value_box.setDecimals(6)
        self.scale_mode_combo.currentTextChanged.connect(self._on_scale_mode_changed)

        form.addRow("SCALE", self.scale_mode_combo)
        form.addRow("SCALE value", self.scale_value_box)

        self.background_type_combo = QComboBox()
        self.background_type_combo.addItems(_BACKGROUND_TYPES)
        self.background_refine_checkbox = QCheckBox("Refine background")
        self.background_refine_checkbox.setChecked(True)
        self.background_value_box = QDoubleSpinBox()
        self.background_value_box.setRange(-1e9, 1e9)
        self.background_value_box.setDecimals(6)
        self.background_type_combo.currentTextChanged.connect(
            self._on_background_type_changed
        )
        self.background_refine_checkbox.toggled.connect(
            self._on_background_type_changed
        )

        form.addRow("Background type", self.background_type_combo)
        form.addRow("", self.background_refine_checkbox)
        form.addRow("Background value", self.background_value_box)

        self.temp_subtract_checkbox = QCheckBox(
            "TEMP_SUBTRACT (requires a fixed SCALE)"
        )
        form.addRow("", self.temp_subtract_checkbox)

        self._on_scale_mode_changed()
        self._on_background_type_changed()
        return group

    # --- interactivity ---------------------------------------------------------

    def _sync_anisotropy_rows(self) -> None:
        if self.spin_dimension_combo.currentIndex() in (0, 1):
            self.anisotropy_table.set_row_count(self.sites_table.row_count())

    def _on_spin_dimension_changed(self) -> None:
        requires_anisotropy = self.spin_dimension_combo.currentIndex() in (0, 1)
        self.anisotropy_table.setEnabled(requires_anisotropy)
        if requires_anisotropy:
            self._sync_anisotropy_rows()

    def _on_ion_changed(self) -> None:
        """The selected ion (and its quenched flag) sets the j0 coefficients,
        C2, and the j2 coefficients (added only when C2 is non-zero)."""
        self._j0_coefficients = self.ion_panel.current_j0()
        self._c2 = self.ion_panel.current_c2()
        if self._c2 != 0.0 and self.ion_panel.has_j2():
            self._j2_coefficients = self.ion_panel.current_j2()
        else:
            self._j2_coefficients = None

    def _on_scale_mode_changed(self) -> None:
        is_fixed = self.scale_mode_combo.currentText() == "Fixed value"
        self.scale_value_box.setEnabled(is_fixed)
        # TEMP_SUBTRACT needs a fixed SCALE (see SpinvertConfig validator).
        self.temp_subtract_checkbox.setEnabled(is_fixed)
        if not is_fixed:
            self.temp_subtract_checkbox.setChecked(False)

    def _on_background_type_changed(self) -> None:
        has_background = self.background_type_combo.currentText() != "None"
        self.background_refine_checkbox.setEnabled(has_background)
        self.background_value_box.setEnabled(
            has_background and not self.background_refine_checkbox.isChecked()
        )

    def _set_scale_from_ion(self, scale: float) -> None:
        self.scale_mode_combo.setCurrentText("Fixed value")
        self.scale_value_box.setValue(scale)

    # --- SpinvertConfig <-> widgets ---------------------------------------------

    def to_config(self, title: str) -> SpinvertConfig:
        """Build a SpinvertConfig from the current form state. Raises
        pydantic.ValidationError if the fields don't form a valid config."""

        cell = CellParameters(
            a=self.cell_a.value(),
            b=self.cell_b.value(),
            c=self.cell_c.value(),
            alpha=self.cell_alpha.value(),
            beta=self.cell_beta.value(),
            gamma=self.cell_gamma.value(),
        )

        dimension_values: tuple[Literal[1], Literal[2], Literal[3]] = (1, 2, 3)
        spin_dimension = dimension_values[self.spin_dimension_combo.currentIndex()]
        anisotropy = (
            self.anisotropy_table.vectors() if spin_dimension in (1, 2) else None
        )

        form_factor_j0 = self._j0_coefficients
        if form_factor_j0 is None:
            raise ValueError("Select a magnetic ion to set the form factor.")
        form_factor_j2 = None
        if self._c2 != 0.0:
            form_factor_j2 = self._j2_coefficients
            if form_factor_j2 is None:
                raise ValueError(
                    "The selected ion has an unquenched orbital moment "
                    f"(C2 = {self._c2:.4g}) but no tabulated J2 form factor. "
                    "Mark the ion as quenched or choose a different ion."
                )

        scale: RefineOrFloat
        if self.scale_mode_combo.currentText() == "REFINE":
            scale = "REFINE"
        else:
            scale = self.scale_value_box.value()

        flat_background: float | str = 0.0
        linear_background: float | str = 0.0
        background_type = self.background_type_combo.currentText()
        if background_type != "None":
            value: RefineOrFloat
            if self.background_refine_checkbox.isChecked():
                value = "REFINE"
            else:
                value = self.background_value_box.value()
            if background_type == "Flat background":
                flat_background = value
            else:
                linear_background = value

        return SpinvertConfig(
            TITLE=title,
            CELL=cell,
            SITE=self.sites_table.vectors(),
            SPIN_DIMENSION=spin_dimension,
            ANISOTROPY=anisotropy,
            FORM_FACTOR_J0=form_factor_j0,
            FORM_FACTOR_J2=form_factor_j2,
            WEIGHT=self.weight_box.value(),
            MOVES=self.moves_box.value(),
            BOX=(self.box_x.value(), self.box_y.value(), self.box_z.value()),
            RUNS=self.runs_box.value(),
            SCALE=scale,
            FLAT_BACKGROUND=flat_background,
            LINEAR_BACKGROUND=linear_background,
            C2=self._c2,
            UISO=self.ion_panel.uiso_box.value(),
            TEMP_SUBTRACT=self.temp_subtract_checkbox.isChecked(),
        )

    def load_config(self, config: SpinvertConfig) -> None:
        """Populate every widget from an existing SpinvertConfig (title excluded)."""

        self.cell_a.setValue(config.cell.a)
        self.cell_b.setValue(config.cell.b)
        self.cell_c.setValue(config.cell.c)
        self.cell_alpha.setValue(config.cell.alpha)
        self.cell_beta.setValue(config.cell.beta)
        self.cell_gamma.setValue(config.cell.gamma)

        self.sites_table.set_vectors(config.sites)

        self.spin_dimension_combo.setCurrentIndex(config.spin_dimension - 1)
        if config.anisotropy:
            self.anisotropy_table.set_vectors(config.anisotropy)

        # Recover the magnetic ion from the loaded form factor(s) so the
        # IonPanel reflects the file, and pick the quenched flag that reproduces
        # the stored C2. The coefficients and C2 are then taken verbatim from
        # the config, so an unrecognised (e.g. hand-edited) form factor still
        # round-trips.
        self.ion_panel.select_matching_ion(config.form_factor_j0, config.form_factor_j2)
        self.ion_panel.match_quenched_to_c2(config.c2)
        self._j0_coefficients = config.form_factor_j0
        self._j2_coefficients = config.form_factor_j2
        self._c2 = config.c2
        self.ion_panel.uiso_box.setValue(config.uiso)

        self.weight_box.setValue(config.weight)
        self.moves_box.setValue(config.moves)
        self.box_x.setValue(config.box[0])
        self.box_y.setValue(config.box[1])
        self.box_z.setValue(config.box[2])
        self.runs_box.setValue(config.runs)

        if config.scale == "REFINE":
            self.scale_mode_combo.setCurrentText("REFINE")
        else:
            self.scale_mode_combo.setCurrentText("Fixed value")
            self.scale_value_box.setValue(config.scale)

        if config.flat_background != 0.0:
            self.background_type_combo.setCurrentText("Flat background")
            self._set_background_mode_and_value(config.flat_background)
        elif config.linear_background != 0.0:
            self.background_type_combo.setCurrentText("Linear background")
            self._set_background_mode_and_value(config.linear_background)
        else:
            self.background_type_combo.setCurrentText("None")

        self.temp_subtract_checkbox.setChecked(config.temp_subtract)

    def _set_background_mode_and_value(self, value: RefineOrFloat) -> None:
        if value == "REFINE":
            self.background_refine_checkbox.setChecked(True)
        else:
            self.background_refine_checkbox.setChecked(False)
            self.background_value_box.setValue(value)

    def try_build_config(
        self, title: str, parent: QWidget | None = None
    ) -> SpinvertConfig | None:
        """Like to_config, but shows a QMessageBox and returns None on failure."""
        try:
            return self.to_config(title)
        except Exception as exc:  # pydantic.ValidationError or plain ValueError
            QMessageBox.critical(parent or self, "Invalid configuration", str(exc))
            return None
