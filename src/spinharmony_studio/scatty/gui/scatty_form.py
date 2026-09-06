"""Widget for editing every field of a :class:`ScattyConfig`."""

import warnings
from typing import get_args

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from spinharmony_studio.scatty.config import (
    Centring,
    Colourmap,
    LaueClass,
    ScatteringAxis,
    ScattyConfig,
    ScattyConfigWarning,
    SummationType,
)

_NONE = "(none)"
_DEFAULT_NAME = "hkl"
# Sampling points auto-filled the moment an axis gets a non-zero direction.
_DEFAULT_AXIS_POINTS = 100

# Explicit labels for the single-character RADIATION codes; default is Neutron.
_RADIATION_CHOICES: list[tuple[str, str]] = [
    ("X-ray", "X"),
    ("Neutron", "N"),
    ("Electron", "E"),
]
_RADIATION_DEFAULT = "N"

# One-click 2-D slices through the origin: (NAME, X_AXIS dir, Y_AXIS dir). The
# third axis is zeroed, so each is a plane that yields a .ppm.
_SLICE_EXTENT = 5.0
_Dir = tuple[float, float, float]
_SLICE_PRESETS: list[tuple[str, _Dir, _Dir]] = [
    ("hk0", (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    ("h0l", (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    ("0kl", (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
]


_SPINBOX_WIDTH = 70


def _vector_boxes() -> list[QDoubleSpinBox]:
    boxes = []
    for _ in range(3):
        box = QDoubleSpinBox()
        box.setRange(-1e4, 1e4)
        box.setDecimals(4)
        box.setFixedWidth(_SPINBOX_WIDTH)
        boxes.append(box)
    return boxes


def _row(*widgets: QWidget) -> QWidget:
    holder = QWidget()
    layout = QHBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    for w in widgets:
        layout.addWidget(w)
    return holder


def _form_layout(parent: QWidget | None = None) -> QFormLayout:
    """A QFormLayout that's aligned to a left-aligned grid on every platform.

    macOS's native style centers QFormLayout and grows fields to fill
    whatever space is left over by default (its SH_FormLayoutFormAlignment
    style hint), unlike Linux/Windows - so left unset, this panel would end
    up centred, with each row's field a different width, instead of a
    consistent left-aligned label/field grid.
    """
    form = QFormLayout(parent)
    form.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
    return form


class ScattyConfigForm(QWidget):
    # Emitted when a quick 2-D slice button is pressed (the fields are filled
    # first); the window connects this to "run scatty".
    run_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.addWidget(self._build_pattern_group())
        layout.addWidget(self._build_expansion_group())
        layout.addWidget(self._build_interpolation_group())
        layout.addWidget(self._build_options_group())
        layout.addWidget(self._build_image_group())
        layout.addStretch()

        self._on_expmax_toggled()
        self._on_exporder_toggled()
        self._on_ppm_output_toggled()
        for key in ("X_AXIS", "Y_AXIS", "Z_AXIS"):
            self._sync_axis_points(key)

    # --- construction -----------------------------------------------------

    def _build_pattern_group(self) -> QGroupBox:
        group = QGroupBox("Scattering pattern")
        form = _form_layout(group)

        self.name_edit = QLineEdit(_DEFAULT_NAME)
        self.name_edit.setPlaceholderText("NAME - goes in the output filenames")
        form.addRow("NAME", self.name_edit)

        self.centre_boxes = _vector_boxes()
        form.addRow("CENTRE (hkl)", _row(*self.centre_boxes))

        self.axis_boxes: dict[str, list[QDoubleSpinBox]] = {}
        self.axis_points: dict[str, QSpinBox] = {}
        for key in ("X_AXIS", "Y_AXIS", "Z_AXIS"):
            boxes = _vector_boxes()
            points = QSpinBox()
            points.setRange(0, 100_000)
            self.axis_boxes[key] = boxes
            self.axis_points[key] = points
            for box in boxes:
                box.valueChanged.connect(
                    lambda _v, k=key: self._sync_axis_points(k, autofill=True)
                )
            form.addRow(key, _row(*boxes, QLabel("points p:"), points))

        slice_row = QHBoxLayout()
        slice_row.setContentsMargins(0, 0, 0, 0)
        for name, _x, _y in _SLICE_PRESETS:
            button = QPushButton(name)
            button.setToolTip(
                f"Fill in a {name} plane through the origin and run Scatty (.ppm)"
            )
            button.clicked.connect(
                lambda _checked, kind=name: self._apply_slice_preset(kind)
            )
            slice_row.addWidget(button)
        holder = QWidget()
        holder.setLayout(slice_row)
        form.addRow("Quick 2-D slices", holder)

        self.radiation_combo = QComboBox()
        for label, code in _RADIATION_CHOICES:
            self.radiation_combo.addItem(label, code)
        self.radiation_combo.setCurrentIndex(
            self.radiation_combo.findData(_RADIATION_DEFAULT)
        )
        form.addRow("RADIATION", self.radiation_combo)
        return group

    def _build_expansion_group(self) -> QGroupBox:
        group = QGroupBox("Displacement expansion (needed for displacive disorder)")
        form = _form_layout(group)

        self.expmax_cb = QCheckBox("EXPANSION_MAX_ERROR")
        self.expmax_cb.toggled.connect(self._on_expmax_toggled)
        self.expmax_spin = QDoubleSpinBox()
        self.expmax_spin.setRange(1e-9, 1.0)
        self.expmax_spin.setDecimals(9)
        self.expmax_spin.setValue(0.05)
        form.addRow(self.expmax_cb, self.expmax_spin)

        self.exporder_cb = QCheckBox("EXPANSION_ORDER")
        self.exporder_cb.toggled.connect(self._on_exporder_toggled)
        self.exporder_spin = QSpinBox()
        self.exporder_spin.setRange(1, 100)
        self.exporder_spin.setValue(10)
        form.addRow(self.exporder_cb, self.exporder_spin)
        return group

    def _build_interpolation_group(self) -> QGroupBox:
        group = QGroupBox("Interpolation and summation")
        form = _form_layout(group)

        self.window_spin = QSpinBox()
        self.window_spin.setRange(0, 50)
        self.window_spin.setValue(3)
        self.window_spin.setToolTip("0 = nearest-neighbour; otherwise an integer >= 2")
        form.addRow("WINDOW (m)", self.window_spin)

        self.cutoff_spin = QSpinBox()
        self.cutoff_spin.setRange(0, 50)
        self.cutoff_spin.setValue(2)
        form.addRow("CUTOFF (m')", self.cutoff_spin)

        self.sum_combo = QComboBox()
        self.sum_combo.addItems(list(get_args(SummationType)))
        form.addRow("SUM", self.sum_combo)
        return group

    def _build_options_group(self) -> QGroupBox:
        group = QGroupBox("Options")
        form = _form_layout(group)

        self.remove_bragg_combo = QComboBox()
        self.remove_bragg_combo.addItems([_NONE, *get_args(Centring)])
        form.addRow("REMOVE_BRAGG (centring)", self.remove_bragg_combo)

        self.symmetry_combo = QComboBox()
        self.symmetry_combo.addItems([_NONE, *get_args(LaueClass)])
        form.addRow("SYMMETRY (Laue class)", self.symmetry_combo)

        self.mag_only_cb = QCheckBox("MAG_ONLY (exclude nuclear scattering)")
        self.temp_subtract_cb = QCheckBox(
            "TEMP_SUBTRACT (subtract ideal paramagnetic background)"
        )
        form.addRow("", self.mag_only_cb)
        form.addRow("", self.temp_subtract_cb)
        return group

    def _build_image_group(self) -> QGroupBox:
        group = QGroupBox("Image / Bragg output")
        form = _form_layout(group)

        self.supercell_cb = QCheckBox("SUPERCELL_BRAGG_OUTPUT (VTK file)")
        form.addRow("", self.supercell_cb)

        self.ppm_output_cb = QCheckBox("PPM_OUTPUT (2-D plots only)")
        self.ppm_output_cb.toggled.connect(self._on_ppm_output_toggled)
        form.addRow("", self.ppm_output_cb)

        # PPM_RANGE always accompanies PPM_OUTPUT; default 0..1, editable.
        self.ppm_min = QDoubleSpinBox()
        self.ppm_max = QDoubleSpinBox()
        for box in (self.ppm_min, self.ppm_max):
            box.setRange(-1e9, 1e9)
            box.setDecimals(6)
        self.ppm_min.setValue(0.0)
        self.ppm_max.setValue(1.0)
        form.addRow("PPM_RANGE", _row(self.ppm_min, QLabel("to"), self.ppm_max))

        self.ppm_cmap_combo = QComboBox()
        self.ppm_cmap_combo.addItems([_NONE, *get_args(Colourmap)])
        form.addRow("PPM_COLOURMAP", self.ppm_cmap_combo)
        return group

    # --- interactivity --------------------------------------------------

    def _on_expmax_toggled(self) -> None:
        self.expmax_spin.setEnabled(self.expmax_cb.isChecked())

    def _on_exporder_toggled(self) -> None:
        self.exporder_spin.setEnabled(self.exporder_cb.isChecked())

    def _on_ppm_output_toggled(self) -> None:
        on = self.ppm_output_cb.isChecked()
        self.ppm_min.setEnabled(on)
        self.ppm_max.setEnabled(on)

    def _sync_axis_points(self, key: str, *, autofill: bool = False) -> None:
        # A zero vector does nothing in Scatty regardless of point count
        # (it collapses that dimension either way) - disable and zero the
        # points box so a config like "Z_AXIS 0 0 0 60" can't be built. When
        # the user first gives an axis a direction, default it to a usable
        # number of sampling points.
        is_zero_vector = not any(box.value() for box in self.axis_boxes[key])
        points = self.axis_points[key]
        points.setEnabled(not is_zero_vector)
        if is_zero_vector:
            points.setValue(0)
        elif autofill and points.value() == 0:
            points.setValue(_DEFAULT_AXIS_POINTS)

    def _apply_slice_preset(self, kind: str) -> None:
        """Fill CENTRE / axes / PPM_OUTPUT for a standard 2-D plane through the
        origin, then ask the window to run Scatty."""
        preset = next((p for p in _SLICE_PRESETS if p[0] == kind), None)
        if preset is None:
            return
        name, x_dir, y_dir = preset
        self.name_edit.setText(name)
        for box in self.centre_boxes:
            box.setValue(0.0)
        vectors = {
            "X_AXIS": tuple(c * _SLICE_EXTENT for c in x_dir),
            "Y_AXIS": tuple(c * _SLICE_EXTENT for c in y_dir),
            "Z_AXIS": (0.0, 0.0, 0.0),
        }
        for axis_key, vec in vectors.items():
            for box, value in zip(self.axis_boxes[axis_key], vec, strict=True):
                box.setValue(value)
            self.axis_points[axis_key].setValue(_DEFAULT_AXIS_POINTS if any(vec) else 0)
            self._sync_axis_points(axis_key)
        self.ppm_output_cb.setChecked(True)
        self._on_ppm_output_toggled()
        self.run_requested.emit()

    # --- ScattyConfig <-> widgets -------------------------------------

    @staticmethod
    def _triple(boxes: list[QDoubleSpinBox]) -> tuple[float, float, float]:
        return (boxes[0].value(), boxes[1].value(), boxes[2].value())

    def to_config(self) -> ScattyConfig:
        data: dict = {
            "NAME": self.name_edit.text().strip(),
            "CENTRE": self._triple(self.centre_boxes),
            "RADIATION": self.radiation_combo.currentData(),
            "WINDOW": self.window_spin.value(),
            "CUTOFF": self.cutoff_spin.value(),
            "SUM": self.sum_combo.currentText(),
            "MAG_ONLY": self.mag_only_cb.isChecked(),
            "TEMP_SUBTRACT": self.temp_subtract_cb.isChecked(),
            "SUPERCELL_BRAGG_OUTPUT": self.supercell_cb.isChecked(),
            "PPM_OUTPUT": self.ppm_output_cb.isChecked(),
        }
        for key in ("X_AXIS", "Y_AXIS", "Z_AXIS"):
            data[key] = {
                "vector": self._triple(self.axis_boxes[key]),
                "points": self.axis_points[key].value(),
            }
        if self.expmax_cb.isChecked():
            data["EXPANSION_MAX_ERROR"] = self.expmax_spin.value()
        if self.exporder_cb.isChecked():
            data["EXPANSION_ORDER"] = self.exporder_spin.value()
        if self.remove_bragg_combo.currentIndex() > 0:
            data["REMOVE_BRAGG"] = self.remove_bragg_combo.currentText()
        if self.symmetry_combo.currentIndex() > 0:
            data["SYMMETRY"] = self.symmetry_combo.currentText()
        if self.ppm_output_cb.isChecked():
            data["PPM_RANGE"] = (self.ppm_min.value(), self.ppm_max.value())
        if self.ppm_cmap_combo.currentIndex() > 0:
            data["PPM_COLOURMAP"] = self.ppm_cmap_combo.currentText()
        return ScattyConfig(**data)

    def build_config_with_warnings(self) -> tuple[ScattyConfig, list[str]]:
        """Build a :class:`ScattyConfig`, also returning any non-fatal
        :class:`ScattyConfigWarning` messages raised while validating it
        (e.g. non-orthogonal axes, or PPM_OUTPUT without a 2-D plane)."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            config = self.to_config()
        messages = [
            str(w.message)
            for w in caught
            if issubclass(w.category, ScattyConfigWarning)
        ]
        return config, messages

    def try_build_config(self, parent: QWidget | None = None) -> ScattyConfig | None:
        try:
            config, config_warnings = self.build_config_with_warnings()
        except Exception as exc:  # pydantic.ValidationError or ValueError
            QMessageBox.critical(
                parent or self, "Invalid scatty configuration", str(exc)
            )
            return None
        if config_warnings:
            QMessageBox.warning(
                parent or self,
                "Scatty configuration warning",
                "\n\n".join(config_warnings),
            )
        return config

    def load_config(self, config: ScattyConfig) -> None:
        self.name_edit.setText(config.name)
        for box, value in zip(self.centre_boxes, config.centre, strict=True):
            box.setValue(value)
        for key, axis in (
            ("X_AXIS", config.x_axis),
            ("Y_AXIS", config.y_axis),
            ("Z_AXIS", config.z_axis),
        ):
            for box, value in zip(self.axis_boxes[key], axis.vector, strict=True):
                box.setValue(value)
            self.axis_points[key].setValue(axis.points)
            self._sync_axis_points(key)
        radiation_idx = self.radiation_combo.findData(config.radiation)
        if radiation_idx >= 0:
            self.radiation_combo.setCurrentIndex(radiation_idx)
        self.window_spin.setValue(config.window)
        self.cutoff_spin.setValue(config.cutoff)
        self.sum_combo.setCurrentText(config.sum_type)
        self.mag_only_cb.setChecked(config.mag_only)
        self.temp_subtract_cb.setChecked(config.temp_subtract)
        self.supercell_cb.setChecked(config.supercell_bragg_output)
        self.ppm_output_cb.setChecked(config.ppm_output)
        self._on_ppm_output_toggled()

        self.expmax_cb.setChecked(config.expansion_max_error is not None)
        if config.expansion_max_error is not None:
            self.expmax_spin.setValue(config.expansion_max_error)
        self.exporder_cb.setChecked(config.expansion_order is not None)
        if config.expansion_order is not None:
            self.exporder_spin.setValue(config.expansion_order)

        self.remove_bragg_combo.setCurrentText(config.remove_bragg or _NONE)
        self.symmetry_combo.setCurrentText(config.symmetry or _NONE)

        if config.ppm_range is not None:
            self.ppm_min.setValue(config.ppm_range[0])
            self.ppm_max.setValue(config.ppm_range[1])
        self.ppm_cmap_combo.setCurrentText(config.ppm_colourmap or _NONE)


__all__ = ["ScattyConfigForm", "ScatteringAxis"]
