"""Tests for :mod:`spinharmony_studio.form_factors`."""

from spinharmony_studio.form_factors import (
    FORM_FACTOR_FIELDS,
    J0_FORM_FACTOR_COEFFICIENTS,
    J2_FORM_FACTOR_COEFFICIENTS,
)


def test_form_factor_fields_has_seven_entries():
    assert FORM_FACTOR_FIELDS == ("A", "a", "B", "b", "C", "c", "D")


def test_j0_table_has_seven_component_entries():
    assert "Fe3+" in J0_FORM_FACTOR_COEFFICIENTS
    assert len(J0_FORM_FACTOR_COEFFICIENTS["Fe3+"]) == 7


def test_j2_table_has_seven_component_entries():
    assert "Tb3+" in J2_FORM_FACTOR_COEFFICIENTS
    assert len(J2_FORM_FACTOR_COEFFICIENTS["Tb3+"]) == 7


def test_entries_can_zip_into_a_coefficients_dict():
    coeffs = dict(
        zip(FORM_FACTOR_FIELDS, J0_FORM_FACTOR_COEFFICIENTS["Fe3+"], strict=True)
    )
    assert set(coeffs) == set(FORM_FACTOR_FIELDS)
