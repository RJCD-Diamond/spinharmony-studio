import math
from functools import cached_property

import mendeleev
from pydantic import BaseModel, computed_field

from spinharmony_studio.form_factors import (
    J0_FORM_FACTOR_COEFFICIENTS,
    J2_FORM_FACTOR_COEFFICIENTS,
)

L_LETTERS = "SPDFGHIKLMN"  # J is skipped by spectroscopic convention
SHELL_L = {"s": 0, "p": 1, "d": 2, "f": 3, "g": 4}


def determine_j(S: float, L: float, n_electrons: int, n_orbitals: int):  # noqa
    """
    Hund's third rule: compare n_electrons to n_orbitals (the shell's
    half-filled point, e.g. 5 for d, 7 for f) and call whichever of the
    three case functions above applies.

    less-than-half-filled: J = |L - S|
    more-than-half-filled: J = L + S
    exactly-half-filled: L = 0, so J = S
    """
    half_filled = n_orbitals

    if n_electrons < half_filled:
        j = abs(L - S)

    elif n_electrons > half_filled:
        j = L + S

    else:
        j = S

    return j


def ground_state_term(n_electrons: int, l_quantum_number: int):
    """
    Apply Hund's rules to a sub-shell of angular momentum quantum number `l`
    (l=2 for d orbitals, l=3 for f orbitals) containing n_electrons, and
    return the ground-state (S, L, J, rule_used) quantum numbers.

    Rule 1: maximize S (fill orbitals singly before pairing).
    Rule 2: maximize L consistent with rule 1 (fill highest ml first, then
            pair from highest ml first).
    Rule 3: J via determine_J() above.


    Returns  S, L, J
    """

    n_orbitals = 2 * l_quantum_number + 1
    max_electrons = 2 * n_orbitals
    if not (0 <= n_electrons <= max_electrons):
        raise ValueError(
            f"n_electrons must be between 0 and {max_electrons} for l={l_quantum_number}"  # noqa
        )

    ml_values = list(
        range(l_quantum_number, -l_quantum_number - 1, -1)
    )  # highest ml first
    occ = {ml: [0, 0] for ml in ml_values}  # [spin_up, spin_down] per orbital

    remaining = n_electrons
    for ml in ml_values:  # Step 1: one spin-up electron per orbital
        if remaining == 0:
            break
        occ[ml][0] = 1
        remaining -= 1
    for ml in ml_values:  # Step 2: pair remaining electrons spin-down
        if remaining == 0:
            break
        occ[ml][1] = 1
        remaining -= 1

    n_up = sum(o[0] for o in occ.values())
    n_down = sum(o[1] for o in occ.values())
    total_ml = sum(ml * (o[0] + o[1]) for ml, o in occ.items())

    S = (n_up - n_down) / 2  # noqa
    L = abs(total_ml)  # noqa
    J = determine_j(S, L, n_electrons, n_orbitals)  # noqa

    return S, L, J


def frac(x: float) -> str:
    # Render integer or half-integer J/S
    if abs(x - round(x)) < 1e-6:
        return str(int(round(x)))
    return f"{int(round(2 * x))}/2"


def term_symbol(S: float, L: float, J: float) -> str:  # noqa
    """Format quantum numbers as a spectroscopic term symbol, e.g. '4F_(9/2)'."""
    multiplicity = int(round(2 * S + 1))
    letter = L_LETTERS[int(round(L))]

    return f"{multiplicity}{letter}_({frac(J)})"


def spin_only_moment(S: float) -> float:  # noqa
    """
    Spin-only magnetic moment (Bohr magnetons):
        mu_s = 2 * sqrt( S(S+1) ) = sqrt( n(n+2) )
    where n is the number of unpaired electrons.

    Used when there is no orbital contribution

    """
    return 2 * math.sqrt(S * (S + 1))


def spin_only_moment_from_unpaired(n_unpaired: int) -> float:
    """
    Spin-only magnetic moment (Bohr magnetons):
        mu_s = 2 * sqrt( S(S+1) ) = sqrt( n(n+2) )
    where n is the number of unpaired electrons.

    Used when there is no orbital contribution

    """
    return math.sqrt(n_unpaired * (n_unpaired + 2))


def lande_g_factor(S: float, L: float, J: float) -> float:  # noqa
    """Lande g-factor for L-S (Russell-Saunders) coupling."""
    if J == 0:
        return 0.0
    return 1 + (J * (J + 1) + S * (S + 1) - L * (L + 1)) / (2 * J * (J + 1))


def spin_orbit_moment(S: float, L: float, J: float) -> float:  # noqa
    """
    Russell-Saunders (spin + orbital) magnetic moment:
        mu = g * sqrt( J(J+1) )
    """
    g = lande_g_factor(S, L, J)
    return g * math.sqrt(J * (J + 1))


def get_outer_electron_config(
    element: str, charge: int | None = None
) -> tuple[str, int, int]:
    """Returns shell, l_quantum_number, n_electrons

    so for Tb3+ -> ('f', 3, 8)
    """

    element_inst = mendeleev.element(element)
    ion = element_inst.ec.ionize(charge) if charge else element_inst.ec
    outer_shell = list(ion.conf.keys())[-1]

    shell = outer_shell[1]
    l_quantum_number = SHELL_L[shell]

    n_electrons = list(ion.conf.values())[-1]

    return shell, l_quantum_number, n_electrons


class MagneticProperties(BaseModel):
    S: float
    L: float
    J: float

    @computed_field
    @cached_property
    def term_symbol(self) -> str:
        return term_symbol(self.S, self.L, self.J)

    @computed_field
    @cached_property
    def mu_spin_only(self) -> float:
        return round(spin_only_moment(self.S), 2)

    @computed_field
    @cached_property
    def lande_g_factor(self) -> float:
        return round(lande_g_factor(self.S, self.L, self.J), 2)

    @computed_field
    @cached_property
    def mu_spin_orbit(self) -> float:
        return round(spin_orbit_moment(self.S, self.L, self.J), 2)

    @computed_field
    @cached_property
    def unpaired_electrons(self) -> int:
        return int(self.S * 2)


def generate_magnetic_properties(
    element: str, charge: int | None = None
) -> MagneticProperties:

    _, l_quantum_number, n_electrons = get_outer_electron_config(element, charge)

    S, L, J = ground_state_term(n_electrons, l_quantum_number)  # noqa

    mag_quantum_numbers = MagneticProperties(S=S, L=L, J=J)

    return mag_quantum_numbers


class MagneticIon(BaseModel):
    element: str
    charge: int | None

    def signed_charge(self):
        """Returns the magnetic ion in the format Cr3+ or Tb3+ or even Fe0+"""
        if self.charge is not None:
            return f"{abs(self.charge)}{'+' if self.charge >= 0 else '-'}"
        else:
            return "0+"

    def get_element_type(self) -> str:
        """Returns the type of the element eg:
        Fe	Iron	Transition metals	d
        La	Lanthanum	Lanthanides	d
        U	Uranium	Actinides	f
        """
        element_inst = mendeleev.element(self.element)
        # print(element_inst.block)  # 'd'
        return element_inst.series  # eg. 'Transition metals'

    def get_c2(self, quenched: bool | None = None) -> float:
        """
        C2 is the ratio of the orbital moment to the total moment

        The magnetic form factor is then given by f(Q) = j0(Q) + C2j2(Q),
        where C2 = Lz /(2Sz + Lz )

        For the lanthanide series, C2 = (2−gJ )/gJ,  where gJ is the
        Landé g-factor.

        For transition metals with unquenched orbital momentum,
        an eﬀective g-factor geﬀ may be defined
        by geﬀSz = 2Sz + Lz , from which C2 = (geﬀ−2)/geﬀ
        (note the diﬀerence in sign compared to the lanthanide case).

        The default value of C2 is 0.
        """

        element_type = self.get_element_type()
        spin_quantum_number = self.magnetic_properties.S
        angular_momentum_quantum_number = self.magnetic_properties.L

        lande_g_factor = self.magnetic_properties.lande_g_factor

        if quenched is None and (element_type == "Transition metals"):
            raise ValueError(
                "For transition metals we must know whether the ion is quenched or not!"
            )

        if (element_type == "Transition metals") and quenched:
            return 0.0
        elif (element_type == "Transition metals") and not quenched:
            return angular_momentum_quantum_number / (
                2 * spin_quantum_number + angular_momentum_quantum_number
            )

        elif (element_type == ("Lanthanides" or "Actinides")) and (
            lande_g_factor != 0.0
        ):
            return (2 - lande_g_factor) / lande_g_factor
        else:
            return 0.0

    @computed_field
    @cached_property
    def magnetic_properties(self) -> MagneticProperties:

        return generate_magnetic_properties(self.element, self.charge)

    def get_j0_form_factor(self) -> tuple:

        return J0_FORM_FACTOR_COEFFICIENTS[f"{self.element}{self.signed_charge()}"]

    def get_j2_form_factor(self) -> tuple:

        return J2_FORM_FACTOR_COEFFICIENTS[f"{self.element}{self.signed_charge()}"]


if __name__ == "__main__":
    for el in ["Co", "La", "Ce", "Pr", "Nd", "Pm", "Sm", "Eu", "Gd", "Tb", "Ho", "Dy"]:
        ion = MagneticIon(element=el, charge=3)

        print(ion.model_dump())
        print(ion.get_c2(quenched=False))
