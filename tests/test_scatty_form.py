"""Tests for :mod:`spinharmony_studio.scatty.gui.scatty_form`."""

from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox

from spinharmony_studio.scatty.config import ScatteringAxis, ScattyConfig
from spinharmony_studio.scatty.gui.scatty_form import ScattyConfigForm

_app = QApplication.instance() or QApplication([])


def _set_axis(form, key, vector, points=None):
    for box, value in zip(form.axis_boxes[key], vector, strict=True):
        box.setValue(value)
    if points is not None:
        form.axis_points[key].setValue(points)


def test_default_name():
    form = ScattyConfigForm()
    assert form.name_edit.text() == "hkl"


def test_default_radiation_is_neutron():
    form = ScattyConfigForm()
    assert form.radiation_combo.currentData() == "N"


def test_axis_points_disabled_for_zero_vector():
    form = ScattyConfigForm()
    assert form.axis_points["X_AXIS"].isEnabled() is False


def test_expmax_spin_enabled_when_checked():
    form = ScattyConfigForm()
    form.expmax_cb.setChecked(True)
    assert form.expmax_spin.isEnabled() is True


def test_expmax_spin_disabled_by_default():
    form = ScattyConfigForm()
    assert form.expmax_spin.isEnabled() is False


def test_exporder_spin_enabled_when_checked():
    form = ScattyConfigForm()
    form.exporder_cb.setChecked(True)
    assert form.exporder_spin.isEnabled() is True


def test_ppm_range_boxes_enabled_with_ppm_output():
    form = ScattyConfigForm()
    assert form.ppm_min.isEnabled() is False
    form.ppm_output_cb.setChecked(True)
    assert form.ppm_min.isEnabled() is True
    assert form.ppm_max.isEnabled() is True


def test_setting_nonzero_vector_enables_and_autofills_points():
    form = ScattyConfigForm()
    form.axis_boxes["X_AXIS"][0].setValue(1.0)
    assert form.axis_points["X_AXIS"].isEnabled() is True
    assert form.axis_points["X_AXIS"].value() == 100


def test_zeroing_vector_disables_and_zeros_points():
    form = ScattyConfigForm()
    form.axis_boxes["X_AXIS"][0].setValue(1.0)
    form.axis_boxes["X_AXIS"][0].setValue(0.0)
    assert form.axis_points["X_AXIS"].isEnabled() is False
    assert form.axis_points["X_AXIS"].value() == 0


def test_autofill_does_not_override_existing_points():
    form = ScattyConfigForm()
    form.axis_points["X_AXIS"].setValue(50)
    form.axis_boxes["X_AXIS"][0].setValue(1.0)
    assert form.axis_points["X_AXIS"].value() == 50


def test_hk0_preset_fills_axes_and_emits_run_requested():
    form = ScattyConfigForm()
    received = []
    form.run_requested.connect(lambda: received.append(True))
    form._apply_slice_preset("hk0")
    assert form.name_edit.text() == "hk0"
    assert form.axis_boxes["X_AXIS"][0].value() == pytest.approx(5.0)
    assert form.axis_boxes["Y_AXIS"][1].value() == pytest.approx(5.0)
    assert form.axis_boxes["Z_AXIS"][0].value() == 0.0
    assert form.ppm_output_cb.isChecked() is True
    assert received == [True]


def test_h0l_preset():
    form = ScattyConfigForm()
    form._apply_slice_preset("h0l")
    assert form.axis_boxes["X_AXIS"][0].value() == pytest.approx(5.0)
    assert form.axis_boxes["Y_AXIS"][2].value() == pytest.approx(5.0)


def test_0kl_preset():
    form = ScattyConfigForm()
    form._apply_slice_preset("0kl")
    assert form.axis_boxes["X_AXIS"][1].value() == pytest.approx(5.0)
    assert form.axis_boxes["Y_AXIS"][2].value() == pytest.approx(5.0)


def test_unknown_preset_is_a_noop():
    form = ScattyConfigForm()
    received = []
    form.run_requested.connect(lambda: received.append(True))
    form._apply_slice_preset("not-a-preset")
    assert received == []


def test_requires_at_least_one_nonzero_axis():
    form = ScattyConfigForm()
    with pytest.raises(Exception, match="must be non-zero"):
        form.to_config()


def test_builds_minimal_valid_config():
    form = ScattyConfigForm()
    _set_axis(form, "X_AXIS", (1.0, 0.0, 0.0), points=10)
    config = form.to_config()
    assert config.name == "hkl"
    assert config.radiation == "N"


def test_expansion_fields_included_when_checked():
    form = ScattyConfigForm()
    _set_axis(form, "X_AXIS", (1.0, 0.0, 0.0), points=10)
    form.expmax_cb.setChecked(True)
    form.expmax_spin.setValue(0.02)
    form.exporder_cb.setChecked(True)
    form.exporder_spin.setValue(5)
    config = form.to_config()
    assert config.expansion_max_error == pytest.approx(0.02)
    assert config.expansion_order == 5


def test_expansion_fields_absent_when_unchecked():
    form = ScattyConfigForm()
    _set_axis(form, "X_AXIS", (1.0, 0.0, 0.0), points=10)
    config = form.to_config()
    assert config.expansion_max_error is None
    assert config.expansion_order is None


def test_remove_bragg_and_symmetry_included_when_selected():
    form = ScattyConfigForm()
    _set_axis(form, "X_AXIS", (1.0, 0.0, 0.0), points=10)
    form.remove_bragg_combo.setCurrentIndex(1)
    form.symmetry_combo.setCurrentIndex(1)
    config = form.to_config()
    assert config.remove_bragg is not None
    assert config.symmetry is not None


def test_ppm_output_includes_range_and_colourmap():
    form = ScattyConfigForm()
    _set_axis(form, "X_AXIS", (1.0, 0.0, 0.0), points=10)
    _set_axis(form, "Y_AXIS", (0.0, 1.0, 0.0), points=10)
    form.ppm_output_cb.setChecked(True)
    form.ppm_min.setValue(0.1)
    form.ppm_max.setValue(0.9)
    form.ppm_cmap_combo.setCurrentIndex(1)
    config = form.to_config()
    assert config.ppm_output is True
    assert config.ppm_range == pytest.approx((0.1, 0.9))
    assert config.ppm_colourmap is not None


def test_mag_only_temp_subtract_supercell_flags():
    form = ScattyConfigForm()
    _set_axis(form, "X_AXIS", (1.0, 0.0, 0.0), points=10)
    form.mag_only_cb.setChecked(True)
    form.temp_subtract_cb.setChecked(True)
    form.supercell_cb.setChecked(True)
    config = form.to_config()
    assert config.mag_only is True
    assert config.temp_subtract is True
    assert config.supercell_bragg_output is True


def test_no_warnings_for_orthogonal_axes():
    form = ScattyConfigForm()
    _set_axis(form, "X_AXIS", (1.0, 0.0, 0.0), points=10)
    _set_axis(form, "Y_AXIS", (0.0, 1.0, 0.0), points=10)
    config, warnings_list = form.build_config_with_warnings()
    assert warnings_list == []


def test_captures_non_orthogonal_axis_warning():
    form = ScattyConfigForm()
    _set_axis(form, "X_AXIS", (1.0, 1.0, 0.0), points=10)
    _set_axis(form, "Y_AXIS", (1.0, 0.0, 0.0), points=10)
    config, warnings_list = form.build_config_with_warnings()
    assert any("orthogonal" in w for w in warnings_list)


def test_returns_config_on_success():
    form = ScattyConfigForm()
    _set_axis(form, "X_AXIS", (1.0, 0.0, 0.0), points=10)
    result = form.try_build_config()
    assert result is not None


def test_invalid_config_shows_critical_and_returns_none():
    form = ScattyConfigForm()  # all axes zero -> invalid
    with patch.object(QMessageBox, "critical") as mock_critical:
        result = form.try_build_config()
    assert result is None
    assert mock_critical.called


def test_warnings_shown_but_config_returned():
    form = ScattyConfigForm()
    _set_axis(form, "X_AXIS", (1.0, 1.0, 0.0), points=10)
    _set_axis(form, "Y_AXIS", (1.0, 0.0, 0.0), points=10)
    with patch.object(QMessageBox, "warning") as mock_warning:
        result = form.try_build_config()
    assert result is not None
    assert mock_warning.called


def test_round_trips_minimal_config():
    form = ScattyConfigForm()
    _set_axis(form, "X_AXIS", (1.0, 0.0, 0.0), points=10)
    original = form.to_config()

    fresh = ScattyConfigForm()
    fresh.load_config(original)
    assert fresh.to_config() == original


def test_round_trips_with_expansion_fields():
    config = ScattyConfig(
        NAME="test",
        X_AXIS=ScatteringAxis(vector=(1.0, 0.0, 0.0), points=10),
        Y_AXIS=ScatteringAxis(vector=(0.0, 1.0, 0.0), points=10),
        Z_AXIS=ScatteringAxis(),
        RADIATION="X",
        EXPANSION_MAX_ERROR=0.02,
        EXPANSION_ORDER=5,
        REMOVE_BRAGG="F",
        SYMMETRY="mmm",
        PPM_OUTPUT=True,
        PPM_RANGE=(0.0, 1.0),
        PPM_COLOURMAP="heat",
        MAG_ONLY=True,
        TEMP_SUBTRACT=True,
        SUPERCELL_BRAGG_OUTPUT=True,
    )
    form = ScattyConfigForm()
    form.load_config(config)
    assert form.expmax_cb.isChecked() is True
    assert form.exporder_cb.isChecked() is True
    assert form.remove_bragg_combo.currentText() == "F"
    assert form.symmetry_combo.currentText() == "mmm"
    assert form.ppm_cmap_combo.currentText() == "heat"
    assert form.radiation_combo.currentData() == "X"
    assert form.to_config() == config


def test_load_config_without_optional_fields_resets_none():
    config = ScattyConfig(
        NAME="test",
        X_AXIS=ScatteringAxis(vector=(1.0, 0.0, 0.0), points=10),
        Y_AXIS=ScatteringAxis(),
        Z_AXIS=ScatteringAxis(),
        RADIATION="N",
    )
    form = ScattyConfigForm()
    form.expmax_cb.setChecked(True)  # pre-existing state should be cleared
    form.load_config(config)
    assert form.expmax_cb.isChecked() is False
    assert form.exporder_cb.isChecked() is False
    assert form.remove_bragg_combo.currentText() == "(none)"
    assert form.symmetry_combo.currentText() == "(none)"
