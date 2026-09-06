"""Tests for :mod:`spinharmony_studio.spinvert.gui.ion_panel`."""

from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QApplication

from spinharmony_studio.moments import MagneticIon
from spinharmony_studio.spinvert.config import FormFactorCoefficients
from spinharmony_studio.spinvert.gui import ion_panel as ion_panel_module
from spinharmony_studio.spinvert.gui.ion_panel import (
    IonPanel,
    _coefficients_from_tuple,
    _coefficients_match,
    _parse_ion_label,
    _sorted_ion_labels,
)

_app = QApplication.instance() or QApplication([])


def test_parses_positive_charge():
    assert _parse_ion_label("Fe3+") == ("Fe", 3)


def test_parses_negative_charge():
    assert _parse_ion_label("Cl1-") == ("Cl", -1)


def test_invalid_label_raises():
    with pytest.raises(ValueError, match="Not a valid ion label"):
        _parse_ion_label("not-an-ion")


def test_returns_sorted_valid_labels():
    labels = _sorted_ion_labels()
    assert len(labels) > 0
    assert labels == sorted(
        labels, key=lambda label: (_parse_ion_label(label)[0], label)
    )


def test_contains_known_ions():
    labels = _sorted_ion_labels()
    assert "Fe3+" in labels
    assert "Tb3+" in labels


def test_coefficients_from_tuple():
    coeffs = _coefficients_from_tuple((1, 2, 3, 4, 5, 6, 7))
    assert coeffs.A == 1
    assert coeffs.D == 7


def test_coefficients_match_true():
    coeffs = FormFactorCoefficients(A=1, a=2, B=3, b=4, C=5, c=6, D=7)
    assert _coefficients_match(coeffs, (1, 2, 3, 4, 5, 6, 7)) is True


def test_coefficients_match_false_on_value_diff():
    coeffs = FormFactorCoefficients(A=1, a=2, B=3, b=4, C=5, c=6, D=7)
    assert _coefficients_match(coeffs, (9, 2, 3, 4, 5, 6, 7)) is False


def test_coefficients_match_false_on_wrong_length():
    coeffs = FormFactorCoefficients(A=1, a=2, B=3, b=4, C=5, c=6, D=7)
    assert _coefficients_match(coeffs, (1, 2, 3)) is False


def test_constructs_and_selects_first_ion():
    panel = IonPanel()
    assert panel.current_ion() is not None
    assert panel.term_symbol_label.text() != "-"


def test_uiso_box_range():
    panel = IonPanel()
    assert panel.uiso_box.minimum() == 0


def test_selecting_lanthanide_disables_and_unchecks_quenched():
    panel = IonPanel()
    panel.ion_combo.setCurrentText("Tb3+")
    assert panel.quenched_checkbox.isEnabled() is False
    assert panel.is_quenched() is False


def test_selecting_transition_metal_enables_quenched():
    panel = IonPanel()
    panel.ion_combo.setCurrentText("Tb3+")  # disable first
    panel.ion_combo.setCurrentText("Fe3+")
    assert panel.quenched_checkbox.isEnabled() is True


def test_current_c2_lanthanide():
    panel = IonPanel()
    panel.ion_combo.setCurrentText("Tb3+")
    assert panel.current_c2() == pytest.approx(1 / 3)


def test_current_c2_transition_metal_quenched_is_zero():
    panel = IonPanel()
    panel.ion_combo.setCurrentText("Fe3+")
    panel.quenched_checkbox.setChecked(True)
    assert panel.current_c2() == 0.0


def test_current_c2_transition_metal_unquenched_nonzero():
    panel = IonPanel()
    panel.ion_combo.setCurrentText("Cr3+")
    panel.quenched_checkbox.setChecked(False)
    assert panel.current_c2() == pytest.approx(0.5)


def test_transition_metal_matches_zero_c2_to_quenched():
    panel = IonPanel()
    panel.ion_combo.setCurrentText("Fe3+")
    panel.quenched_checkbox.setChecked(False)
    panel.match_quenched_to_c2(0.0)
    assert panel.quenched_checkbox.isChecked() is True


def test_transition_metal_matches_nonzero_c2_to_unquenched():
    panel = IonPanel()
    panel.ion_combo.setCurrentText("Fe3+")
    panel.quenched_checkbox.setChecked(True)
    panel.match_quenched_to_c2(0.5)
    assert panel.quenched_checkbox.isChecked() is False


def test_lanthanide_is_a_noop():
    panel = IonPanel()
    panel.ion_combo.setCurrentText("Tb3+")
    before = panel.quenched_checkbox.isChecked()
    panel.match_quenched_to_c2(0.0)
    assert panel.quenched_checkbox.isChecked() == before


def test_matches_single_candidate():
    panel = IonPanel()
    target = panel.current_j0()  # whichever ion is first
    assert target is not None
    expected_label = panel.ion_combo.currentText()
    panel.ion_combo.setCurrentText("Tb3+")  # move away first
    result = panel.select_matching_ion(target)
    assert result is True
    assert panel.ion_combo.currentText() == expected_label


def test_no_match_returns_false():
    panel = IonPanel()
    bogus = FormFactorCoefficients(A=999, a=999, B=999, b=999, C=999, c=999, D=999)
    assert panel.select_matching_ion(bogus) is False


def test_disambiguates_via_j2_when_j0_shared():
    # Real element symbols (mendeleev needs to resolve them when
    # IonPanel._recompute() runs on construction/selection) sharing a
    # synthetic j0 table but distinct j2 tables, so select_matching_ion
    # must fall back to j2 to disambiguate.
    shared_j0 = (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0)
    fake_j0 = {"He1+": shared_j0, "Ne1+": shared_j0}
    fake_j2 = {
        "He1+": (10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0),
        "Ne1+": (11.0, 21.0, 31.0, 41.0, 51.0, 61.0, 71.0),
    }
    with (
        patch.object(ion_panel_module, "J0_FORM_FACTOR_COEFFICIENTS", fake_j0),
        patch.object(ion_panel_module, "J2_FORM_FACTOR_COEFFICIENTS", fake_j2),
    ):
        # Construct while patched so the combo box's own items (populated
        # from _sorted_ion_labels() at __init__ time) include the
        # synthetic labels select_matching_ion needs to select between.
        panel = IonPanel()
        j0_target = _coefficients_from_tuple(shared_j0)
        j2_target = _coefficients_from_tuple(fake_j2["Ne1+"])
        result = panel.select_matching_ion(j0_target, j2_target)
        assert result is True
        assert panel.ion_combo.currentText() == "Ne1+"


def test_j2_narrowing_with_no_match_keeps_all_candidates():
    shared_j0 = (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0)
    fake_j0 = {"He1+": shared_j0, "Ne1+": shared_j0}
    fake_j2 = {"He1+": (10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0)}
    with (
        patch.object(ion_panel_module, "J0_FORM_FACTOR_COEFFICIENTS", fake_j0),
        patch.object(ion_panel_module, "J2_FORM_FACTOR_COEFFICIENTS", fake_j2),
    ):
        panel = IonPanel()
        j0_target = _coefficients_from_tuple(shared_j0)
        unmatched_j2 = _coefficients_from_tuple(
            (999.0, 999.0, 999.0, 999.0, 999.0, 999.0, 999.0)
        )
        result = panel.select_matching_ion(j0_target, unmatched_j2)
        assert result is True  # falls back to the unnarrowed candidate list


def test_has_j2_true_for_known_ion():
    panel = IonPanel()
    panel.ion_combo.setCurrentText("Fe3+")
    assert panel.has_j2() is True


def test_current_j0_returns_coefficients():
    panel = IonPanel()
    panel.ion_combo.setCurrentText("Fe3+")
    assert panel.current_j0() is not None


def test_current_j2_returns_none_on_keyerror():
    panel = IonPanel()
    panel.ion_combo.setCurrentText("Fe3+")
    with patch.object(MagneticIon, "get_j2_form_factor", side_effect=KeyError("no j2")):
        assert panel.current_j2() is None
        assert panel.has_j2() is False


def test_emits_spin_only_moment_squared_when_quenched():
    panel = IonPanel()
    panel.ion_combo.setCurrentText("Fe3+")
    panel.quenched_checkbox.setChecked(True)
    received = []
    panel.apply_scale_requested.connect(received.append)
    panel.emit_scale()
    current_ion = panel.current_ion()
    assert current_ion is not None
    expected = current_ion.magnetic_properties.mu_spin_only**2
    assert received == [pytest.approx(expected)]


def test_emits_spin_orbit_moment_squared_when_unquenched():
    panel = IonPanel()
    panel.ion_combo.setCurrentText("Cr3+")
    panel.quenched_checkbox.setChecked(False)
    received = []
    panel.apply_scale_requested.connect(received.append)
    panel.emit_scale()
    current_ion = panel.current_ion()
    assert current_ion is not None
    expected = current_ion.magnetic_properties.mu_spin_orbit**2
    assert received == [pytest.approx(expected)]


def test_ion_changed_emitted_on_selection_change():
    panel = IonPanel()
    received = []
    panel.ion_changed.connect(lambda: received.append(True))
    panel.ion_combo.setCurrentText("Tb3+")
    assert received
