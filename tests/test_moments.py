"""Tests for :mod:`spinharmony_studio.moments`."""

import math

import pytest

from spinharmony_studio.moments import (
    MagneticIon,
    MagneticProperties,
    determine_j,
    frac,
    generate_magnetic_properties,
    get_outer_electron_config,
    ground_state_term,
    lande_g_factor,
    spin_only_moment,
    spin_only_moment_from_unpaired,
    spin_orbit_moment,
    term_symbol,
)


def test_less_than_half_filled():
    assert determine_j(S=1.5, L=3, n_electrons=3, n_orbitals=5) == 1.5


def test_more_than_half_filled():
    assert determine_j(S=1.5, L=3, n_electrons=8, n_orbitals=5) == 4.5


def test_exactly_half_filled():
    assert determine_j(S=2.5, L=0, n_electrons=5, n_orbitals=5) == 2.5


def test_tb3plus_f8():
    # Tb3+ (f8): known ground state term is 7F6.
    S, L, J = ground_state_term(8, 3)  # noqa
    assert (S, L, J) == (3.0, 3, 6.0)


def test_fe3plus_d5_half_filled():
    # Fe3+ (d5, half-filled): 6S(5/2), L=0.
    S, L, J = ground_state_term(5, 2)  # noqa
    assert (S, L, J) == (2.5, 0, 2.5)


def test_cr3plus_d3_less_than_half_filled():
    S, L, J = ground_state_term(3, 2)  # noqa
    assert (S, L, J) == (1.5, 3, 1.5)


def test_zero_electrons():
    assert ground_state_term(0, 2) == (0.0, 0, 0.0)


def test_fully_filled_shell():
    assert ground_state_term(10, 2) == (0.0, 0, 0.0)


def test_out_of_range_raises():
    with pytest.raises(ValueError, match="n_electrons must be between"):
        ground_state_term(11, 2)


def test_negative_raises():
    with pytest.raises(ValueError):
        ground_state_term(-1, 2)


def test_integer():
    assert frac(3.0) == "3"


def test_half_integer():
    assert frac(2.5) == "5/2"


def test_negative_zero_like():
    assert frac(0.0) == "0"


def test_tb3plus():
    assert term_symbol(3.0, 3, 6.0) == "7F_(6)"


def test_fe3plus():
    assert term_symbol(2.5, 0, 2.5) == "6S_(5/2)"


def test_spin_only_moment():
    assert spin_only_moment(2.5) == pytest.approx(5.916079783099616)


def test_spin_only_moment_zero():
    assert spin_only_moment(0.0) == 0.0


def test_spin_only_moment_from_unpaired_matches_spin_formula():
    # n unpaired electrons <-> S = n/2; both formulas must agree.
    n = 5
    assert spin_only_moment_from_unpaired(n) == pytest.approx(spin_only_moment(n / 2))


def test_lande_g_factor_j_zero_is_zero():
    assert lande_g_factor(3, 3, 0) == 0.0


def test_lande_g_factor_tb3plus():
    assert lande_g_factor(3, 3, 6) == pytest.approx(1.5)


def test_spin_orbit_moment_tb3plus():
    assert spin_orbit_moment(3, 3, 6) == pytest.approx(9.72111104761179)


def test_spin_orbit_moment_zero_when_j_zero():
    assert spin_orbit_moment(3, 3, 0) == 0.0


def test_tb3plus_is_f8():
    assert get_outer_electron_config("Tb", 3) == ("f", 3, 8)


def test_fe3plus_is_d5():
    assert get_outer_electron_config("Fe", 3) == ("d", 2, 5)


def test_neutral_atom_no_charge():
    # Neutral Fe's outer subshell (by mendeleev's conf ordering) is 4s,
    # not 3d - ionizing (charge=3) is what strips those to expose 3d.
    shell, l, n = get_outer_electron_config("Fe")  # noqa
    assert shell == "s"
    assert l == 0


def test_computed_fields_for_tb3plus():
    props = generate_magnetic_properties("Tb", 3)
    assert isinstance(props, MagneticProperties)
    assert props.S == 3.0
    assert props.L == 3
    assert props.J == 6.0
    assert props.term_symbol == "7F_(6)"
    assert props.mu_spin_only == pytest.approx(6.928203)
    assert props.lande_g_factor == pytest.approx(1.5)
    assert props.mu_spin_orbit == pytest.approx(9.721111)
    assert props.unpaired_electrons == 6


def test_signed_charge_positive():
    ion = MagneticIon(element="Tb", charge=3)
    assert ion.signed_charge() == "3+"


def test_signed_charge_negative():
    ion = MagneticIon(element="Cl", charge=-1)
    assert ion.signed_charge() == "1-"


def test_signed_charge_none():
    ion = MagneticIon(element="Fe", charge=None)
    assert ion.signed_charge() == "0+"


def test_get_element_type_lanthanide():
    ion = MagneticIon(element="Tb", charge=3)
    assert ion.get_element_type() == "Lanthanides"


def test_get_element_type_transition_metal():
    ion = MagneticIon(element="Fe", charge=3)
    assert ion.get_element_type() == "Transition metals"


def test_transition_metal_requires_quenched_argument():
    ion = MagneticIon(element="Fe", charge=3)
    with pytest.raises(ValueError, match="quenched"):
        ion.get_c2()


def test_transition_metal_quenched_is_zero():
    ion = MagneticIon(element="Fe", charge=3)
    assert ion.get_c2(quenched=True) == 0.0


def test_transition_metal_unquenched_nonzero_orbital():
    # Cr3+ (d3): S=1.5, L=3 -> total=2*1.5+3=6, C2=3/6=0.5.
    ion = MagneticIon(element="Cr", charge=3)
    assert ion.get_c2(quenched=False) == pytest.approx(0.5)


def test_transition_metal_unquenched_zero_total_returns_zero():
    # Zn2+ (d10, closed shell): S=0, L=0 -> total=0, avoids division by zero.
    ion = MagneticIon(element="Zn", charge=2)
    assert ion.get_c2(quenched=False) == 0.0


def test_lanthanide_c2_from_lande_g_factor():
    # Tb3+: g=1.5 -> C2 = (2-1.5)/1.5 = 1/3.
    ion = MagneticIon(element="Tb", charge=3)
    assert ion.get_c2() == pytest.approx(1 / 3)


def test_lanthanide_with_zero_g_factor_falls_back_to_zero():
    # Eu3+ (f6): ground state J=0 -> lande_g_factor=0 -> final else branch.
    ion = MagneticIon(element="Eu", charge=3)
    assert ion.magnetic_properties.lande_g_factor == 0.0
    assert ion.get_c2() == 0.0


def test_magnetic_properties_cached_property():
    ion = MagneticIon(element="Tb", charge=3)
    first = ion.magnetic_properties
    assert ion.magnetic_properties is first


def test_get_j0_form_factor():
    ion = MagneticIon(element="Fe", charge=3)
    coeffs = ion.get_j0_form_factor()
    assert len(coeffs) == 7


def test_get_j2_form_factor():
    ion = MagneticIon(element="Fe", charge=3)
    coeffs = ion.get_j2_form_factor()
    assert len(coeffs) == 7


def test_spin_only_moment_matches_unpaired_electron_relationship():
    # sqrt(n(n+2)) form should equal 2*sqrt(S(S+1)) for S=n/2.
    for n in range(0, 8):
        S = n / 2  # noqa
        assert spin_only_moment(S) == pytest.approx(math.sqrt(n * (n + 2)))
