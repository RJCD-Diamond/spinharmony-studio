"""Tests for :mod:`spinharmony_studio.spinvert.gui.config_form`."""

from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox

from spinharmony_studio.spinvert.gui.config_form import ConfigFormWidget

_app = QApplication.instance() or QApplication([])


def test_defaults_to_heisenberg():
    form = ConfigFormWidget()
    assert form.spin_dimension_combo.currentText() == "3 - Heisenberg"
    assert form.anisotropy_table.isEnabled() is False


def test_starts_with_one_site():
    form = ConfigFormWidget()
    assert form.sites_table.row_count() == 1


def test_ion_panel_selected_by_default():
    form = ConfigFormWidget()
    assert form._j0_coefficients is not None


def test_switching_to_ising_enables_anisotropy():
    form = ConfigFormWidget()
    form.spin_dimension_combo.setCurrentIndex(0)  # Ising
    assert form.anisotropy_table.isEnabled() is True


def test_switching_to_ising_syncs_anisotropy_row_count():
    form = ConfigFormWidget()
    form.sites_table.add_row()
    form.sites_table.add_row()
    form.spin_dimension_combo.setCurrentIndex(0)
    assert form.anisotropy_table.row_count() == form.sites_table.row_count()


def test_adding_site_while_ising_syncs_anisotropy():
    form = ConfigFormWidget()
    form.spin_dimension_combo.setCurrentIndex(1)  # XY
    form.sites_table.add_row()
    assert form.anisotropy_table.row_count() == form.sites_table.row_count()


def test_adding_site_while_heisenberg_does_not_sync():
    form = ConfigFormWidget()
    before = form.anisotropy_table.row_count()
    form.sites_table.add_row()
    assert form.anisotropy_table.row_count() == before


def test_selecting_ion_updates_coefficients():
    form = ConfigFormWidget()
    form.ion_panel.ion_combo.setCurrentText("Fe3+")
    assert form._j0_coefficients == form.ion_panel.current_j0()


def test_apply_scale_button_sets_fixed_scale():
    form = ConfigFormWidget()
    form.ion_panel.ion_combo.setCurrentText("Fe3+")
    form.ion_panel.quenched_checkbox.setChecked(True)
    form.apply_scale_button.click()
    assert form.scale_mode_combo.currentText() == "Fixed value"
    current_ion = form.ion_panel.current_ion()
    assert current_ion is not None
    expected = current_ion.magnetic_properties.mu_spin_only**2
    assert form.scale_value_box.value() == pytest.approx(expected)


def test_scale_value_box_disabled_when_refine():
    form = ConfigFormWidget()
    form.scale_mode_combo.setCurrentText("REFINE")
    assert form.scale_value_box.isEnabled() is False
    assert form.temp_subtract_checkbox.isEnabled() is False


def test_scale_value_box_enabled_when_fixed():
    form = ConfigFormWidget()
    form.scale_mode_combo.setCurrentText("Fixed value")
    assert form.scale_value_box.isEnabled() is True
    assert form.temp_subtract_checkbox.isEnabled() is True


def test_switching_back_to_refine_unchecks_temp_subtract():
    form = ConfigFormWidget()
    form.scale_mode_combo.setCurrentText("Fixed value")
    form.temp_subtract_checkbox.setChecked(True)
    form.scale_mode_combo.setCurrentText("REFINE")
    assert form.temp_subtract_checkbox.isChecked() is False


def test_background_none_disables_controls():
    form = ConfigFormWidget()
    form.background_type_combo.setCurrentText("None")
    assert form.background_refine_checkbox.isEnabled() is False
    assert form.background_value_box.isEnabled() is False


def test_background_flat_enables_refine_checkbox():
    form = ConfigFormWidget()
    form.background_type_combo.setCurrentText("Flat background")
    assert form.background_refine_checkbox.isEnabled() is True


def test_background_value_box_disabled_while_refine_checked():
    form = ConfigFormWidget()
    form.background_type_combo.setCurrentText("Flat background")
    form.background_refine_checkbox.setChecked(True)
    assert form.background_value_box.isEnabled() is False


def test_background_value_box_enabled_when_not_refining():
    form = ConfigFormWidget()
    form.background_type_combo.setCurrentText("Flat background")
    form.background_refine_checkbox.setChecked(False)
    assert form.background_value_box.isEnabled() is True


def test_builds_valid_default_config():
    form = ConfigFormWidget()
    config = form.to_config("MyTitle")
    assert config.title == "MyTitle"
    assert config.spin_dimension == 3
    assert config.anisotropy is None


def test_ising_config_includes_anisotropy():
    form = ConfigFormWidget()
    form.spin_dimension_combo.setCurrentIndex(0)
    config = form.to_config("Ising")
    assert config.spin_dimension == 1
    assert config.anisotropy is not None
    assert len(config.anisotropy) == form.sites_table.row_count()


def test_missing_j0_raises():
    form = ConfigFormWidget()
    form._j0_coefficients = None
    with pytest.raises(ValueError, match="Select a magnetic ion"):
        form.to_config("Foo")


def test_nonzero_c2_without_j2_raises():
    form = ConfigFormWidget()
    form._c2 = 0.5
    form._j2_coefficients = None
    with pytest.raises(ValueError, match="no tabulated J2"):
        form.to_config("Foo")


def test_nonzero_c2_with_j2_included():
    form = ConfigFormWidget()
    form.ion_panel.ion_combo.setCurrentText("Cr3+")
    form.ion_panel.quenched_checkbox.setChecked(False)
    form._on_ion_changed()
    config = form.to_config("Foo")
    assert config.c2 != 0.0
    assert config.form_factor_j2 is not None


def test_fixed_scale_used():
    form = ConfigFormWidget()
    form.scale_mode_combo.setCurrentText("Fixed value")
    form.scale_value_box.setValue(42.0)
    config = form.to_config("Foo")
    assert config.scale == 42.0


def test_flat_background_refine():
    form = ConfigFormWidget()
    form.background_type_combo.setCurrentText("Flat background")
    form.background_refine_checkbox.setChecked(True)
    config = form.to_config("Foo")
    assert config.flat_background == "REFINE"


def test_flat_background_fixed_value():
    form = ConfigFormWidget()
    form.background_type_combo.setCurrentText("Flat background")
    form.background_refine_checkbox.setChecked(False)
    form.background_value_box.setValue(3.5)
    config = form.to_config("Foo")
    assert config.flat_background == 3.5


def test_linear_background_fixed_value():
    form = ConfigFormWidget()
    form.background_type_combo.setCurrentText("Linear background")
    form.background_refine_checkbox.setChecked(False)
    form.background_value_box.setValue(2.0)
    config = form.to_config("Foo")
    assert config.linear_background == 2.0


def test_box_and_weight_and_runs():
    form = ConfigFormWidget()
    form.weight_box.setValue(0.5)
    form.moves_box.setValue(1000)
    form.box_x.setValue(2)
    form.box_y.setValue(3)
    form.box_z.setValue(4)
    form.runs_box.setValue(7)
    config = form.to_config("Foo")
    assert config.weight == 0.5
    assert config.moves == 1000
    assert config.box == (2, 3, 4)
    assert config.runs == 7


def test_round_trips_heisenberg_config():
    form = ConfigFormWidget()
    form.ion_panel.ion_combo.setCurrentText("Fe3+")
    original = form.to_config("RoundTrip")

    fresh = ConfigFormWidget()
    fresh.load_config(original)
    reloaded = fresh.to_config("RoundTrip")
    assert reloaded == original


def test_round_trips_ising_config_with_anisotropy():
    form = ConfigFormWidget()
    form.spin_dimension_combo.setCurrentIndex(0)
    form.ion_panel.ion_combo.setCurrentText("Fe3+")
    form.ion_panel.quenched_checkbox.setChecked(True)
    original = form.to_config("Ising")

    fresh = ConfigFormWidget()
    fresh.load_config(original)
    assert fresh.spin_dimension_combo.currentIndex() == 0
    assert original.anisotropy is not None
    assert fresh.anisotropy_table.vectors() == list(original.anisotropy)


def test_load_config_sets_fixed_scale():
    form = ConfigFormWidget()
    form.ion_panel.ion_combo.setCurrentText("Fe3+")
    form.scale_mode_combo.setCurrentText("Fixed value")
    form.scale_value_box.setValue(12.5)
    original = form.to_config("Foo")

    fresh = ConfigFormWidget()
    fresh.load_config(original)
    assert fresh.scale_mode_combo.currentText() == "Fixed value"
    assert fresh.scale_value_box.value() == pytest.approx(12.5)


def test_load_config_sets_refine_background():
    form = ConfigFormWidget()
    form.ion_panel.ion_combo.setCurrentText("Fe3+")
    form.scale_mode_combo.setCurrentText("Fixed value")
    form.scale_value_box.setValue(1.0)
    form.background_type_combo.setCurrentText("Flat background")
    form.background_refine_checkbox.setChecked(True)
    original = form.to_config("Foo")

    fresh = ConfigFormWidget()
    fresh.load_config(original)
    assert fresh.background_type_combo.currentText() == "Flat background"
    assert fresh.background_refine_checkbox.isChecked() is True


def test_load_config_sets_fixed_background_value():
    form = ConfigFormWidget()
    form.ion_panel.ion_combo.setCurrentText("Fe3+")
    form.scale_mode_combo.setCurrentText("Fixed value")
    form.scale_value_box.setValue(1.0)
    form.background_type_combo.setCurrentText("Linear background")
    form.background_refine_checkbox.setChecked(False)
    form.background_value_box.setValue(4.2)
    original = form.to_config("Foo")

    fresh = ConfigFormWidget()
    fresh.load_config(original)
    assert fresh.background_type_combo.currentText() == "Linear background"
    assert fresh.background_value_box.value() == pytest.approx(4.2)


def test_load_config_no_background():
    form = ConfigFormWidget()
    form.ion_panel.ion_combo.setCurrentText("Fe3+")
    original = form.to_config("Foo")

    fresh = ConfigFormWidget()
    fresh.load_config(original)
    assert fresh.background_type_combo.currentText() == "None"


def test_load_config_sets_temp_subtract():
    form = ConfigFormWidget()
    form.ion_panel.ion_combo.setCurrentText("Fe3+")
    form.scale_mode_combo.setCurrentText("Fixed value")
    form.scale_value_box.setValue(1.0)
    form.temp_subtract_checkbox.setChecked(True)
    original = form.to_config("Foo")

    fresh = ConfigFormWidget()
    fresh.load_config(original)
    assert fresh.temp_subtract_checkbox.isChecked() is True


def test_returns_config_on_success():
    form = ConfigFormWidget()
    config = form.try_build_config("Foo")
    assert config is not None
    assert config.title == "Foo"


def test_returns_none_and_shows_dialog_on_failure():
    form = ConfigFormWidget()
    form._j0_coefficients = None
    with patch.object(QMessageBox, "critical") as mock_critical:
        result = form.try_build_config("Foo")
    assert result is None
    assert mock_critical.called
