"""Magnetic-ion selector: drives FormFactorCoefficients, C2 and SCALE from
MagneticIon, per the J0/J2 form-factor tables in form_factors.py.
"""

import math
import re

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QWidget,
)

from spinharmony_studio.form_factors import (
    J0_FORM_FACTOR_COEFFICIENTS,
    J2_FORM_FACTOR_COEFFICIENTS,
)
from spinharmony_studio.moments import MagneticIon
from spinharmony_studio.spinvert.config import (
    FORM_FACTOR_FIELDS,
    FormFactorCoefficients,
)

_ION_LABEL_RE = re.compile(r"^([A-Za-z]+)(\d+)([+-])$")


def _parse_ion_label(label: str) -> tuple[str, int]:
    match = _ION_LABEL_RE.match(label)
    if not match:
        raise ValueError(f"Not a valid ion label: {label!r}")
    element, digits, sign = match.groups()
    charge = int(digits) * (1 if sign == "+" else -1)
    return element, charge


def _sorted_ion_labels() -> list[str]:
    labels = [key for key in J0_FORM_FACTOR_COEFFICIENTS if _ION_LABEL_RE.match(key)]
    return sorted(labels, key=lambda label: (_parse_ion_label(label)[0], label))


def _coefficients_from_tuple(values: tuple) -> FormFactorCoefficients:
    return FormFactorCoefficients(**dict(zip(FORM_FACTOR_FIELDS, values, strict=True)))


def _coefficients_match(model: FormFactorCoefficients, values: tuple) -> bool:
    if len(values) != len(FORM_FACTOR_FIELDS):
        return False
    return all(
        math.isclose(getattr(model, field), value, rel_tol=1e-6, abs_tol=1e-9)
        for field, value in zip(FORM_FACTOR_FIELDS, values, strict=True)
    )


class IonPanel(QGroupBox):
    """Lets the user pick a magnetic ion. The j0/j2 form-factor coefficients and
    the C2 orbital/total moment ratio follow the selection (and the "orbital
    moment quenched" checkbox) automatically; the effective moment can be pushed
    into SCALE on demand."""

    ion_changed = pyqtSignal()
    apply_scale_requested = pyqtSignal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Magnetic ion", parent)

        self.ion_combo = QComboBox()
        self.ion_combo.addItems(_sorted_ion_labels())
        self.ion_combo.currentTextChanged.connect(self._recompute)

        self.quenched_checkbox = QCheckBox("Orbital moment quenched")
        self.quenched_checkbox.setChecked(True)
        self.quenched_checkbox.setToolTip(
            "Transition metals only: quenched -> C2 = 0 (j0 only, spin-only "
            "moment); unquenched -> C2 = L / (2S + L) and the j2 term is added. "
            "Lanthanides and actinides are always unquenched."
        )
        self.quenched_checkbox.toggled.connect(self._recompute)

        self.term_symbol_label = QLabel("-")
        self.s_l_j_label = QLabel("-")
        self.g_factor_label = QLabel("-")
        self.mu_spin_only_label = QLabel("-")
        self.mu_spin_orbit_label = QLabel("-")
        self.c2_label = QLabel("-")

        self.uiso_box = QDoubleSpinBox()
        self.uiso_box.setRange(0, 1e6)
        self.uiso_box.setDecimals(6)
        self.uiso_box.setFixedWidth(70)

        form = QFormLayout()
        # macOS centers QFormLayout and grows fields to fill leftover space
        # by default (unlike Linux/Windows); force a left-aligned grid so
        # this matches the rest of the configuration panel.
        form.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        form.addRow("Ion", self.ion_combo)
        form.addRow("", self.quenched_checkbox)
        form.addRow("Term symbol", self.term_symbol_label)
        form.addRow("S, L, J", self.s_l_j_label)
        form.addRow("g factor", self.g_factor_label)
        form.addRow("mu (spin-only)", self.mu_spin_only_label)
        form.addRow("mu (spin-orbit)", self.mu_spin_orbit_label)
        form.addRow("C2", self.c2_label)
        form.addRow("UISO", self.uiso_box)

        self.setLayout(form)

        self._recompute()

    def current_ion(self) -> MagneticIon | None:
        label = self.ion_combo.currentText()
        if not label:
            return None
        element, charge = _parse_ion_label(label)
        return MagneticIon(element=element, charge=charge)

    def is_quenched(self) -> bool:
        return self.quenched_checkbox.isChecked()

    def current_c2(self) -> float:
        ion = self.current_ion()
        if ion is None:
            return 0.0
        try:
            return ion.get_c2(quenched=self.quenched_checkbox.isChecked())
        except Exception:
            return 0.0

    def match_quenched_to_c2(self, target_c2: float) -> None:
        """When loading a config, choose the quenched flag that reproduces the
        stored C2. Only meaningful for transition metals; a no-op otherwise."""
        ion = self.current_ion()
        if ion is None or not self._is_transition_metal(ion):
            return
        self.quenched_checkbox.setChecked(target_c2 == 0)

    def select_matching_ion(
        self,
        j0: FormFactorCoefficients,
        j2: FormFactorCoefficients | None = None,
    ) -> bool:
        """Point the ion selector at the ion whose tabulated form factor(s)
        match the given coefficients. When several ions share a j0 table, j2
        (if supplied) is used to disambiguate. Returns True on a match."""
        candidates = [
            label
            for label in _sorted_ion_labels()
            if _coefficients_match(j0, J0_FORM_FACTOR_COEFFICIENTS[label])
        ]
        if j2 is not None and len(candidates) > 1:
            narrowed = [
                label
                for label in candidates
                if label in J2_FORM_FACTOR_COEFFICIENTS
                and _coefficients_match(j2, J2_FORM_FACTOR_COEFFICIENTS[label])
            ]
            if narrowed:
                candidates = narrowed
        if not candidates:
            return False
        if self.ion_combo.currentText() != candidates[0]:
            self.ion_combo.setCurrentText(candidates[0])
        return True

    def has_j2(self) -> bool:
        ion = self.current_ion()
        return ion is not None and self._has_j2(ion)

    def current_j0(self) -> FormFactorCoefficients | None:
        ion = self.current_ion()
        if ion is None:
            return None
        return _coefficients_from_tuple(ion.get_j0_form_factor())

    def current_j2(self) -> FormFactorCoefficients | None:
        ion = self.current_ion()
        if ion is None:
            return None
        try:
            coeffs = ion.get_j2_form_factor()
        except KeyError:
            return None
        return _coefficients_from_tuple(coeffs)

    def _recompute(self) -> None:
        ion = self.current_ion()
        if ion is None:
            return

        # Lanthanides / actinides are never quenched; lock the checkbox off.
        # A transition metal defaults to quenched (the usual 3d assumption);
        # moving between two transition metals preserves the user's choice.
        is_transition_metal = self._is_transition_metal(ion)
        was_enabled = self.quenched_checkbox.isEnabled()
        self.quenched_checkbox.blockSignals(True)
        self.quenched_checkbox.setEnabled(is_transition_metal)
        if not is_transition_metal:
            self.quenched_checkbox.setChecked(False)
        elif not was_enabled:
            self.quenched_checkbox.setChecked(True)
        self.quenched_checkbox.blockSignals(False)

        props = ion.magnetic_properties
        self.term_symbol_label.setText(props.term_symbol)
        self.s_l_j_label.setText(f"{props.S}, {props.L}, {props.J}")
        self.g_factor_label.setText(str(props.lande_g_factor))
        self.mu_spin_only_label.setText(f"{props.mu_spin_only} uB")
        self.mu_spin_orbit_label.setText(f"{props.mu_spin_orbit} uB")

        c2 = self.current_c2()
        if c2 != 0.0 and not self._has_j2(ion):
            self.c2_label.setText(f"{c2:.6g}  (no J2 table for this ion!)")
        else:
            self.c2_label.setText(f"{c2:.6g}")

        self.ion_changed.emit()

    @staticmethod
    def _has_j2(ion: MagneticIon) -> bool:
        try:
            ion.get_j2_form_factor()
        except KeyError:
            return False
        return True

    @staticmethod
    def _is_transition_metal(ion: MagneticIon) -> bool:
        try:
            return ion.get_element_type() == "Transition metals"
        except Exception:
            return False

    def emit_scale(self) -> None:
        """Emit apply_scale_requested with the selected ion's mu^2 (spin-only
        when the orbital moment is quenched, spin-orbit otherwise)."""
        ion = self.current_ion()
        if ion is None:
            return
        props = ion.magnetic_properties
        moment = (
            props.mu_spin_only
            if self.quenched_checkbox.isChecked()
            else props.mu_spin_orbit
        )
        self.apply_scale_requested.emit(moment * moment)
