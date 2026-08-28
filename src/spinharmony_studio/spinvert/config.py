"""
Pydantic model(s) representing a Spinvert [title]_config.txt file.

Based on the keyword spec:
  Required: TITLE, CELL, SITE, SPIN_DIMENSION, ANISOTROPY (conditional),
            FORM_FACTOR_J0, WEIGHT, MOVES, BOX
  Optional: RUNS, SCALE, FLAT_BACKGROUND, LINEAR_BACKGROUND, C2,
            FORM_FACTOR_J2 (conditional on C2), UISO, TEMP_SUBTRACT
"""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from spinharmony_studio.config_base import FortranConfig

# A "REFINE" sentinel or a fixed numeric value.
RefineOrFloat = float | Literal["REFINE"]

Vector3 = tuple[float, float, float] | list[float]

# Field order for CELL and FORM_FACTOR_J0/J2 lines, used for both parsing
# and export so the two stay in sync automatically.
CELL_FIELDS = ("a", "b", "c", "alpha", "beta", "gamma")
FORM_FACTOR_FIELDS = ("A", "a", "B", "b", "C", "c", "D")


class CellParameters(BaseModel):
    """CELL keyword: lattice parameters a, b, c (Angstrom)
    and angles alpha, beta, gamma (degrees)."""

    a: float = Field(gt=0)
    b: float = Field(gt=0)
    c: float = Field(gt=0)
    alpha: float = Field(gt=0, lt=180)
    beta: float = Field(gt=0, lt=180)
    gamma: float = Field(gt=0, lt=180)


class FormFactorCoefficients(BaseModel):
    """Analytical-approximation coefficients for j0(Q) or j2(Q): A, a, B, b, C, c, D."""

    A: float
    a: float
    B: float
    b: float
    C: float
    c: float
    D: float


def _to_float_or_refine(token: str) -> RefineOrFloat:
    """Parse a token that is either the literal REFINE (case-insensitive)
    or a numeric value."""
    if token.strip().upper() == "REFINE":
        return "REFINE"
    return float(token)


def _fmt_num(value: float) -> str:
    """Format a float with enough precision for a clean round trip while
    still trimming needless trailing digits/zeros."""
    return f"{value:.10g}"


def _fmt_refine_or_float(value: RefineOrFloat) -> str:
    return value if isinstance(value, str) else _fmt_num(value)


def _fmt_vector(vector: Vector3) -> str:
    return " ".join(_fmt_num(component) for component in vector)


def _require_n_values(values: list[str], n: int, keyword: str, line: str) -> None:
    if len(values) != n:
        raise ValueError(f"{keyword} expects {n} values, got: {line!r}")


def _parse_vector3(
    values: list[str], keyword: str, line: str
) -> tuple[float, float, float]:
    """Parse exactly three floats into a fixed-length tuple (rather than
    tuple(...) over a generator, whose length a type checker can't infer)."""
    _require_n_values(values, 3, keyword, line)
    x, y, z = (float(v) for v in values)
    return (x, y, z)


def parse_spinvert_config_text(text: str) -> dict:
    """Parse the contents of a Spinvert [title]_config.txt file into a dict
    of keyword -> value(s) keyed by the file's own keyword names, suitable
    for constructing a SpinvertConfig directly, e.g. SpinvertConfig(**parsed).

    Handles:
      - Whitespace-insensitive, repeated lines for SITE / ANISOTROPY
      - Case-insensitive keywords
      - Blank lines and leading/trailing whitespace
      - Bare flag keywords with no trailing value (e.g. TEMP_SUBTRACT)
      - REFINE sentinel for SCALE / FLAT_BACKGROUND / LINEAR_BACKGROUND
    """
    data: dict = {}
    sites: list[tuple[float, float, float]] = []
    anisotropy: list[tuple[float, float, float]] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", "!")):
            continue

        keyword_token, *values = line.split()
        keyword = keyword_token.upper()

        if keyword == "TITLE":
            # Preserve everything after the keyword itself, in case the
            # title contains internal whitespace.
            data["TITLE"] = line[len(keyword_token) :].strip()

        elif keyword == "CELL":
            _require_n_values(values, 6, keyword, line)
            floats = (float(v) for v in values)
            data["CELL"] = dict(zip(CELL_FIELDS, floats, strict=True))

        elif keyword == "SITE":
            sites.append(_parse_vector3(values, keyword, line))

        elif keyword == "ANISOTROPY":
            anisotropy.append(_parse_vector3(values, keyword, line))

        elif keyword == "SPIN_DIMENSION":
            data["SPIN_DIMENSION"] = int(values[0])

        elif keyword in ("FORM_FACTOR_J0", "FORM_FACTOR_J2"):
            _require_n_values(values, 7, keyword, line)
            coeffs = (float(v) for v in values)
            data[keyword] = dict(zip(FORM_FACTOR_FIELDS, coeffs, strict=True))

        elif keyword == "WEIGHT":
            data["WEIGHT"] = float(values[0])

        elif keyword == "MOVES":
            data["MOVES"] = int(values[0])

        elif keyword == "BOX":
            _require_n_values(values, 3, keyword, line)
            data["BOX"] = tuple(int(float(v)) for v in values)

        elif keyword == "RUNS":
            data["RUNS"] = int(values[0])

        elif keyword in ("SCALE", "FLAT_BACKGROUND", "LINEAR_BACKGROUND"):
            data[keyword] = _to_float_or_refine(values[0])

        elif keyword == "C2":
            data["C2"] = float(values[0])

        elif keyword == "UISO":
            data["UISO"] = float(values[0])

        elif keyword == "TEMP_SUBTRACT":
            data["TEMP_SUBTRACT"] = (
                values[0].strip().upper() not in ("0", "FALSE", "NO", "OFF")
                if values
                else True  # bare flag with no trailing value means "on"
            )

        else:
            raise ValueError(f"Unrecognised keyword {keyword!r} in line: {line!r}")

    if sites:
        data["SITE"] = sites
    if anisotropy:
        data["ANISOTROPY"] = anisotropy

    return data


class SpinvertConfig(FortranConfig):
    # File-saving behaviour (to_text / to_file / formatting helpers) is inherited
    # from FortranConfig; only _config_lines below is Spinvert-specific.

    # --- Required keywords ---
    title: str = Field(alias="TITLE")
    cell: CellParameters = Field(alias="CELL")
    sites: list[Vector3] = Field(alias="SITE", min_length=1)
    spin_dimension: Literal[1, 2, 3] = Field(alias="SPIN_DIMENSION")
    form_factor_j0: FormFactorCoefficients = Field(alias="FORM_FACTOR_J0")
    weight: float = Field(default=1, alias="WEIGHT", gt=0)
    moves: int = Field(default=300, alias="MOVES", gt=0)
    box: tuple[int, int, int] = Field(default=(5, 5, 5), alias="BOX")

    # --- Conditionally required ---
    anisotropy: list[Vector3] | None = Field(default=None, alias="ANISOTROPY")
    form_factor_j2: FormFactorCoefficients | None = Field(
        default=None, alias="FORM_FACTOR_J2"
    )

    # --- Optional keywords with defaults ---
    runs: int = Field(default=1, alias="RUNS", gt=0)
    scale: RefineOrFloat = Field(default="REFINE", alias="SCALE")
    flat_background: RefineOrFloat = Field(default=0.0, alias="FLAT_BACKGROUND")
    linear_background: RefineOrFloat = Field(default=0.0, alias="LINEAR_BACKGROUND")
    c2: float = Field(default=0.0, alias="C2")
    uiso: float = Field(default=0.0, alias="UISO", ge=0)
    temp_subtract: bool = Field(default=False, alias="TEMP_SUBTRACT")

    # --- Cross-field validation ---

    @model_validator(mode="after")
    def _check_box_positive(self) -> "SpinvertConfig":
        if any(n <= 0 for n in self.box):
            raise ValueError("BOX must contain three positive integers.")
        return self

    @model_validator(mode="after")
    def _check_anisotropy(self) -> "SpinvertConfig":
        # Required for Ising (1) or XY (2) spins; not applicable for Heisenberg (3).
        if self.spin_dimension in (1, 2):
            if not self.anisotropy:
                raise ValueError(
                    "ANISOTROPY is required when SPIN_DIMENSION is 1 (Ising) or 2 (XY)."
                )
            if len(self.anisotropy) != len(self.sites):
                raise ValueError(
                    "ANISOTROPY must supply exactly one vector per SITE "
                    f"({len(self.sites)} sites, "
                    f"{len(self.anisotropy)} anisotropy vectors given)."
                )
        elif self.spin_dimension == 3 and self.anisotropy:
            raise ValueError(
                "ANISOTROPY should not be given for "
                "Heisenberg (SPIN_DIMENSION=3) spins."
            )
        return self

    @model_validator(mode="after")
    def _check_form_factor_j2(self) -> "SpinvertConfig":
        if self.c2 != 0 and self.form_factor_j2 is None:
            raise ValueError("FORM_FACTOR_J2 is required when C2 is non-zero.")
        return self

    @model_validator(mode="after")
    def _check_backgrounds_mutually_exclusive(self) -> "SpinvertConfig":
        if self.flat_background != 0.0 and self.linear_background != 0.0:
            raise ValueError(
                "FLAT_BACKGROUND and LINEAR_BACKGROUND cannot both be "
                "specified simultaneously."
            )
        return self

    @model_validator(mode="after")
    def _check_temp_subtract_requires_fixed_scale(self) -> "SpinvertConfig":
        if self.temp_subtract and self.scale == "REFINE":
            raise ValueError(
                "When TEMP_SUBTRACT is set, SCALE must be a fixed numeric value "
                "(the squared effective magnetic moment, mu^2), not REFINE."
            )
        return self

    # --- Import ---

    @classmethod
    def from_text(cls, text: str) -> "SpinvertConfig":
        """Construct a SpinvertConfig from the raw text of a
        [title]_config.txt file."""
        return cls(**parse_spinvert_config_text(text))

    @classmethod
    def from_file(cls, path: str | Path) -> "SpinvertConfig":
        """Construct a SpinvertConfig by reading a [title]_config.txt file."""
        return cls.from_text(Path(path).read_text())

    # --- Export ---

    @classmethod
    def _check_output_name(cls, name: str) -> None:
        # Spinvert config files are named [title]_config.txt (variable stem).
        if not name.endswith("_config.txt"):
            raise ValueError(
                f"Spinvert config files must be named [title]_config.txt, not {name!r}."
            )

    def _config_lines(self) -> list[str]:
        """Render this config back into Spinvert's [title]_config.txt format."""
        j0 = self.form_factor_j0
        lines = [
            f"TITLE {self.title}",
            "CELL "
            + _fmt_vector((self.cell.a, self.cell.b, self.cell.c))
            + " "
            + _fmt_vector((self.cell.alpha, self.cell.beta, self.cell.gamma)),
            *(f"SITE {_fmt_vector(site)}" for site in self.sites),
            f"SPIN_DIMENSION {self.spin_dimension}",
            *(f"ANISOTROPY {_fmt_vector(vec)}" for vec in self.anisotropy or ()),
            "FORM_FACTOR_J0 "
            + " ".join(_fmt_num(getattr(j0, field)) for field in FORM_FACTOR_FIELDS),
        ]

        if self.form_factor_j2:
            j2 = self.form_factor_j2
            coeffs = " ".join(
                _fmt_num(getattr(j2, field)) for field in FORM_FACTOR_FIELDS
            )
            lines.append(f"FORM_FACTOR_J2 {coeffs}")

        lines += [
            f"WEIGHT {_fmt_num(self.weight)}",
            f"MOVES {self.moves}",
            f"BOX {self.box[0]} {self.box[1]} {self.box[2]}",
        ]

        if self.runs != 1:
            lines.append(f"RUNS {self.runs}")

        lines.append(f"SCALE {_fmt_refine_or_float(self.scale)}")

        if self.flat_background != 0.0:
            value = _fmt_refine_or_float(self.flat_background)
            lines.append(f"FLAT_BACKGROUND {value}")
        if self.linear_background != 0.0:
            value = _fmt_refine_or_float(self.linear_background)
            lines.append(f"LINEAR_BACKGROUND {value}")

        if self.c2 != 0.0:
            lines.append(f"C2 {_fmt_num(self.c2)}")
        if self.uiso != 0.0:
            lines.append(f"UISO {_fmt_num(self.uiso)}")
        if self.temp_subtract:
            lines.append("TEMP_SUBTRACT")

        return lines


if __name__ == "__main__":
    example = SpinvertConfig(
        TITLE="Example",
        CELL=CellParameters(a=8.5, b=8.5, c=8.5, alpha=90, beta=90, gamma=90),
        SITE=[(0.125, 0.125, 0.125), (0.875, 0.875, 0.875)],
        SPIN_DIMENSION=3,
        FORM_FACTOR_J0=FormFactorCoefficients(
            A=0.422, a=17.684, B=0.5948, b=6.005, C=0.0043, c=-0.609, D=0.0
        ),
        WEIGHT=0.05,
        MOVES=5000,
        BOX=(6, 6, 6),
        RUNS=10,
        SCALE="REFINE",
    )
    print(example.model_dump_json(indent=2, by_alias=True))

    example.to_file("/workspaces/spinharmony_studio/src/example_config.txt")
