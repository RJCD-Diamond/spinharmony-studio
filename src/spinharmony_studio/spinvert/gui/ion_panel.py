"""Magnetic-ion selector: drives FormFactorCoefficients and SCALE from
MagneticIon, per the J0/J2 form-factor tables in form_factors.py.
"""

import math
import re

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
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
    """Lets the user pick a magnetic ion. The j0 (and, when available, j2)
    form-factor coefficients follow the selection automatically; the effective
    moment can be pushed into SCALE on demand."""

    ion_changed = pyqtSignal()
    apply_scale_requested = pyqtSignal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Magnetic ion", parent)

        self.ion_combo = QComboBox()
        self.ion_combo.addItems(_sorted_ion_labels())
        self.ion_combo.currentTextChanged.connect(self._recompute)

        self.term_symbol_label = QLabel("-")
        self.s_l_j_label = QLabel("-")
        self.g_factor_label = QLabel("-")
        self.mu_spin_only_label = QLabel("-")
        self.mu_spin_orbit_label = QLabel("-")

        form = QFormLayout()
        form.addRow("Ion", self.ion_combo)
        form.addRow("Term symbol", self.term_symbol_label)
        form.addRow("S, L, J", self.s_l_j_label)
        form.addRow("g factor", self.g_factor_label)
        form.addRow("mu (spin-only)", self.mu_spin_only_label)
        form.addRow("mu (spin-orbit)", self.mu_spin_orbit_label)

        self.apply_scale_spin_only_button = QPushButton("Spin-only mu^2 as SCALE")
        self.apply_scale_spin_orbit_button = QPushButton("Spin-orbit mu^2 as SCALE")
        self.apply_scale_spin_only_button.clicked.connect(
            lambda: self._emit_scale(spin_only=True)
        )
        self.apply_scale_spin_orbit_button.clicked.connect(
            lambda: self._emit_scale(spin_only=False)
        )

        buttons = QHBoxLayout()
        buttons.addWidget(self.apply_scale_spin_only_button)
        buttons.addWidget(self.apply_scale_spin_orbit_button)
        buttons.addStretch()

        outer = QFormLayout()
        self.setLayout(outer)
        outer.addRow(form)
        outer.addRow(buttons)

        self._recompute()

    def current_ion(self) -> MagneticIon | None:
        label = self.ion_combo.currentText()
        if not label:
            return None
        element, charge = _parse_ion_label(label)
        return MagneticIon(element=element, charge=charge)

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

        props = ion.magnetic_properties
        self.term_symbol_label.setText(props.term_symbol)
        self.s_l_j_label.setText(f"{props.S}, {props.L}, {props.J}")
        self.g_factor_label.setText(str(props.lande_g_factor))
        self.mu_spin_only_label.setText(f"{props.mu_spin_only} uB")
        self.mu_spin_orbit_label.setText(f"{props.mu_spin_orbit} uB")

        self.ion_changed.emit()

    @staticmethod
    def _has_j2(ion: MagneticIon) -> bool:
        try:
            ion.get_j2_form_factor()
        except KeyError:
            return False
        return True

    def _emit_scale(self, *, spin_only: bool) -> None:
        ion = self.current_ion()
        if ion is None:
            return
        props = ion.magnetic_properties
        moment = props.mu_spin_only if spin_only else props.mu_spin_orbit
        self.apply_scale_requested.emit(moment * moment)
