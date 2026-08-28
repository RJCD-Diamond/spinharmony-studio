"""Pydantic model representing a Scatty ``scatty_config.txt`` file.

The file is a list of capitalised keywords, each usually followed by numbers or
a short string, in any order, with ``#`` / ``!`` comment lines allowed.
"""

import warnings
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from spinharmony_studio.config_base import (
    FortranConfig,
    require_n,
    split_config_lines,
)

Radiation = Literal["X", "N", "E"]
Centring = Literal["P", "I", "F", "R", "A", "B", "C", "H"]
SummationType = Literal["PARALLEL", "SPHERE"]
Colourmap = Literal["default", "heat", "jet", "grey1", "grey2"]
# The 11 Laue classes, written as Scatty expects them.
LaueClass = Literal[
    "m-3m",
    "m-3",
    "6|mmm",
    "6|m",
    "-3m",
    "-3",
    "4|mmm",
    "4|m",
    "mmm",
    "2|m",
    "-1",
]


class ScattyConfigWarning(UserWarning):
    """Non-fatal issue in a scatty_config.txt, mirroring a warning Scatty
    itself would print (e.g. non-orthogonal scattering axes)."""


class ScatteringAxis(BaseModel):
    """One axis of the calculated pattern: a reciprocal-space vector in hkl
    units and the number of sampling points ``p``. Scatty calculates ``2p+1``
    points from ``CENTRE - vector`` to ``CENTRE + vector``. A zero axis
    (``0 0 0 0``) drops that dimension, so a plane or a line is calculated."""

    vector: tuple[float, float, float] = (0.0, 0.0, 0.0)
    points: int = Field(default=0, ge=0)

    @property
    def is_zero(self) -> bool:
        return self.points == 0 and not any(self.vector)


class ScattyConfig(FortranConfig):
    # --- Required keywords ---
    name: str = Field(alias="NAME")
    x_axis: ScatteringAxis = Field(alias="X_AXIS")
    y_axis: ScatteringAxis = Field(alias="Y_AXIS")
    z_axis: ScatteringAxis = Field(alias="Z_AXIS")
    radiation: Radiation = Field(alias="RADIATION")

    # --- Optional keywords with defaults ---
    centre: tuple[float, float, float] = Field(default=(0.0, 0.0, 0.0), alias="CENTRE")
    window: int = Field(default=3, alias="WINDOW")
    cutoff: int = Field(default=2, alias="CUTOFF", ge=0)
    sum_type: SummationType = Field(default="PARALLEL", alias="SUM")
    mag_only: bool = Field(default=False, alias="MAG_ONLY")
    temp_subtract: bool = Field(default=False, alias="TEMP_SUBTRACT")
    supercell_bragg_output: bool = Field(default=False, alias="SUPERCELL_BRAGG_OUTPUT")
    ppm_output: bool = Field(default=False, alias="PPM_OUTPUT")

    # --- Optional keywords, absent unless given ---
    expansion_max_error: float | None = Field(
        default=None, alias="EXPANSION_MAX_ERROR", gt=0
    )
    expansion_order: int | None = Field(default=None, alias="EXPANSION_ORDER", ge=1)
    remove_bragg: Centring | None = Field(default=None, alias="REMOVE_BRAGG")
    symmetry: LaueClass | None = Field(default=None, alias="SYMMETRY")
    ppm_range: tuple[float, float] | None = Field(default=None, alias="PPM_RANGE")
    ppm_colourmap: Colourmap | None = Field(default=None, alias="PPM_COLOURMAP")

    # --- Cross-field validation ---

    @model_validator(mode="after")
    def _check_window(self) -> "ScattyConfig":
        if self.window < 0 or self.window == 1:
            raise ValueError(
                "WINDOW must be 0 (nearest-neighbour interpolation) or an "
                "integer >= 2 (Lanczos window)."
            )
        return self

    @model_validator(mode="after")
    def _check_axes(self) -> "ScattyConfig":
        nonzero = [
            axis for axis in (self.x_axis, self.y_axis, self.z_axis) if not axis.is_zero
        ]
        if not nonzero:
            raise ValueError(
                "At least one of X_AXIS / Y_AXIS / Z_AXIS must be non-zero; "
                "otherwise there is nothing to calculate."
            )
        for i, first in enumerate(nonzero):
            for second in nonzero[i + 1 :]:
                dot = sum(
                    a * b for a, b in zip(first.vector, second.vector, strict=True)
                )
                norms = (sum(c * c for c in first.vector) ** 0.5) * (
                    sum(c * c for c in second.vector) ** 0.5
                )
                if norms and abs(dot) > 1e-6 * norms:
                    warnings.warn(
                        "The non-zero scattering axes do not appear to be "
                        f"mutually orthogonal (dot product {dot:g}); Scatty "
                        "expects X/Y/Z to be orthogonal.",
                        ScattyConfigWarning,
                        stacklevel=2,
                    )
        return self

    @model_validator(mode="after")
    def _check_ppm_range(self) -> "ScattyConfig":
        if self.ppm_range is not None and self.ppm_range[0] >= self.ppm_range[1]:
            raise ValueError("PPM_RANGE must be given as 'min max' with min < max.")
        return self

    # --- Import ---

    @classmethod
    def from_text(cls, text: str) -> "ScattyConfig":
        """Construct a ScattyConfig from the raw text of a scatty_config.txt."""
        data: dict = {}
        for keyword, values in split_config_lines(text):
            if keyword == "NAME":
                data["NAME"] = " ".join(values)
            elif keyword == "CENTRE":
                require_n(values, 3, keyword)
                data["CENTRE"] = tuple(float(v) for v in values)
            elif keyword in ("X_AXIS", "Y_AXIS", "Z_AXIS"):
                require_n(values, 4, keyword)
                *vec, count = values
                data[keyword] = {
                    "vector": tuple(float(v) for v in vec),
                    "points": int(count),
                }
            elif keyword == "RADIATION":
                data["RADIATION"] = values[0].upper()
            elif keyword == "EXPANSION_MAX_ERROR":
                data["EXPANSION_MAX_ERROR"] = float(values[0])
            elif keyword == "EXPANSION_ORDER":
                data["EXPANSION_ORDER"] = int(values[0])
            elif keyword == "REMOVE_BRAGG":
                data["REMOVE_BRAGG"] = values[0].upper()
            elif keyword == "WINDOW":
                data["WINDOW"] = int(values[0])
            elif keyword == "CUTOFF":
                data["CUTOFF"] = int(values[0])
            elif keyword == "SUM":
                data["SUM"] = values[0].upper()
            elif keyword in (
                "MAG_ONLY",
                "TEMP_SUBTRACT",
                "SUPERCELL_BRAGG_OUTPUT",
                "PPM_OUTPUT",
            ):
                # bare flags: present -> on (a trailing 0/false/no/off -> off)
                data[keyword] = not (
                    values and values[0].strip().upper() in ("0", "FALSE", "NO", "OFF")
                )
            elif keyword == "SYMMETRY":
                data["SYMMETRY"] = values[0]
            elif keyword == "PPM_RANGE":
                require_n(values, 2, keyword)
                data["PPM_RANGE"] = tuple(float(v) for v in values)
            elif keyword == "PPM_COLOURMAP":
                data["PPM_COLOURMAP"] = values[0].lower()
            else:
                raise ValueError(
                    f"Unrecognised keyword {keyword!r} in scatty_config.txt"
                )
        return cls(**data)

    @classmethod
    def from_file(cls, path: str | Path) -> "ScattyConfig":
        """Construct a ScattyConfig by reading a scatty_config.txt file."""
        return cls.from_text(Path(path).read_text())

    # --- Export ---

    def _config_lines(self) -> list[str]:
        kw = self.keyword
        lines = [kw("NAME", self.name)]

        if any(self.centre):
            lines.append(kw("CENTRE", self.centre))

        for keyword, axis in (
            ("X_AXIS", self.x_axis),
            ("Y_AXIS", self.y_axis),
            ("Z_AXIS", self.z_axis),
        ):
            lines.append(kw(keyword, axis.vector, axis.points))

        lines.append(kw("RADIATION", self.radiation))

        if self.expansion_max_error is not None:
            lines.append(kw("EXPANSION_MAX_ERROR", self.expansion_max_error))
        if self.expansion_order is not None:
            lines.append(kw("EXPANSION_ORDER", self.expansion_order))
        if self.remove_bragg is not None:
            lines.append(kw("REMOVE_BRAGG", self.remove_bragg))
        if self.window != 3:
            lines.append(kw("WINDOW", self.window))
        if self.cutoff != 2:
            lines.append(kw("CUTOFF", self.cutoff))
        if self.sum_type != "PARALLEL":
            lines.append(kw("SUM", self.sum_type))
        if self.mag_only:
            lines.append(kw("MAG_ONLY"))
        if self.temp_subtract:
            lines.append(kw("TEMP_SUBTRACT"))
        if self.symmetry is not None:
            lines.append(kw("SYMMETRY", self.symmetry))
        if self.supercell_bragg_output:
            lines.append(kw("SUPERCELL_BRAGG_OUTPUT"))
        if self.ppm_output:
            lines.append(kw("PPM_OUTPUT"))
        if self.ppm_range is not None:
            lines.append(kw("PPM_RANGE", self.ppm_range))
        if self.ppm_colourmap is not None:
            lines.append(kw("PPM_COLOURMAP", self.ppm_colourmap))

        return lines

    def to_file(self, path: str | Path) -> Path:
        config_filename = "scatty_config.txt"

        if not str(path).endswith(config_filename):
            raise ValueError(f"config filename must be {config_filename}")

        path = Path(path)
        self._check_output_name(path.name)
        path.write_text(self.to_text())
        return path


if __name__ == "__main__":
    example = ScattyConfig(
        NAME="hk0 plane",
        X_AXIS=ScatteringAxis(vector=(4.0, 0.0, 0.0), points=200),
        Y_AXIS=ScatteringAxis(vector=(0.0, 4.0, 0.0), points=200),
        Z_AXIS=ScatteringAxis(vector=(0.0, 0.0, 0.0), points=0),
        RADIATION="N",
        EXPANSION_MAX_ERROR=0.05,
        REMOVE_BRAGG="F",
        SYMMETRY="4|mmm",
        PPM_OUTPUT=True,
        PPM_COLOURMAP="jet",
    )
