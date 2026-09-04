"""Convert SPINVERT refinement output into CrystalMaker .cmtx files.

SPINVERT (https://spinvert.chem.ox.ac.uk/) writes fitted spin configurations
as plain-text ``*_spins_NN.txt`` files. This module turns one of those files
into a CrystalMaker ``.cmtx`` file that plots the magnetic atoms with their
refined spin vectors as arrows.

Optionally, if a matching ``*scf.txt`` spin-correlation file is present, a
second ``.cmtx`` file is produced in which every magnetic atom is relabelled
``Up``/``Dw`` according to whether its correlation with the atom nearest the
centre of the supercell is ferromagnetic or antiferromagnetic. Give those two
labels distinct colours/styles in CrystalMaker for the clearest result.

Run as a script (edit the ``SpinvertConfig`` in :func:`main`), or import the
public functions/classes to build a custom pipeline.

"""

from __future__ import annotations

import logging
import string
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from itertools import product
from pathlib import Path
from typing import TextIO

import numpy as np
from mendeleev import element as mendeleev_element
from scipy.spatial import KDTree

logger = logging.getLogger(__name__)

_FALLBACK_BOND_LENGTH_ANGSTROM = 1.5


def bond_length_from_element(symbol: str) -> float:
    """Derive an AVEC arrow length (Angstrom) from an element's covalent radius.

    Looks up ``symbol`` with `mendeleev <https://mendeleev.readthedocs.io/>`_
    and converts its tabulated covalent radius from picometres to Angstrom.
    Falls back to :data:`_FALLBACK_BOND_LENGTH_ANGSTROM` (with a warning) if
    the element is unknown or has no tabulated covalent radius.
    """
    try:
        covalent_radius_pm = mendeleev_element(symbol).covalent_radius
    except Exception:  # unknown symbol, network/db lookup failure, etc.
        covalent_radius_pm = None
        logger.warning("mendeleev has no data for element %r", symbol)

    if covalent_radius_pm is None:
        logger.warning(
            "No covalent radius available for %r; falling back to %.2f \u00c5",
            symbol,
            _FALLBACK_BOND_LENGTH_ANGSTROM,
        )
        return _FALLBACK_BOND_LENGTH_ANGSTROM

    return covalent_radius_pm / 100.0


# A symmetry operator maps fractional coordinate arrays (x, y, z) to an
# equivalent-position fractional coordinate array (x', y', z').
SymmetryOp = Callable[
    [np.ndarray, np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray, np.ndarray]
]


def default_symmetry_operations() -> list[SymmetryOp]:
    """Symmetry operators used by the original script (space group P2_1/n).

    Supply a different list of operators via
    :attr:`SpinvertConfig.symmetry_operations` for other space groups.
    """
    return [
        lambda x, y, z: (x, y, z),
        lambda x, y, z: (1.5 - x, 1.0 - y, z + 0.5),
        lambda x, y, z: (1.0 - x, y + 0.5, 1.5 - z),
        lambda x, y, z: (x + 0.5, 1.5 - y, 1.0 - z),
    ]


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class VectorStyle:
    """Rendering style for the AVEC spin-vector arrows in a .cmtx file.

    Leave ``bond_length`` as ``None`` to derive it automatically from the
    magnetic atom's covalent radius via :func:`bond_length_from_element`;
    set it explicitly to override that lookup.
    """

    bond_length: float | None = None
    colour_rgb: tuple[float, float, float] = (0.0, 0.0, 1.0)
    style: int = 3

    def resolved(self, magnetic_atom: str) -> VectorStyle:
        """Return a copy with ``bond_length`` filled in if not already set."""
        if self.bond_length is not None:
            return self
        bond_length = bond_length_from_element(magnetic_atom)
        logger.info(
            "Derived AVEC bond length %.3f \u00c5 from %s's covalent radius (mendeleev)",  # noqa
            bond_length,
            magnetic_atom,
        )
        return replace(self, bond_length=bond_length)


@dataclass(frozen=True)
class FerroHighlightSettings:
    """Settings controlling the ferro/antiferromagnetic highlighting pass."""

    enabled: bool = True
    correlation_cutoff: float = 0.04  # inspect the scf.txt plot to choose this
    atom_distance: float = 3.0  # Angstrom cutoff for including non-magnetic atoms
    highlight_center_atom: bool = False
    up_label: str = "Up"
    down_label: str = "Dw"


@dataclass(frozen=True)
class NonMagneticAtom:
    """A symmetry-independent non-magnetic atom in the asymmetric unit."""

    element: str
    fractional_position: tuple[float, float, float]


@dataclass(frozen=True)
class SpinvertConfig:
    """All user-configurable parameters for a spins -> .cmtx conversion."""

    data_dir: Path
    magnetic_atom: str
    non_magnetic_atoms: Sequence[NonMagneticAtom]
    symmetry_operations: Sequence[SymmetryOp] = field(
        default_factory=default_symmetry_operations
    )
    vector_style: VectorStyle = field(default_factory=VectorStyle)
    ferro_highlight: FerroHighlightSettings = field(
        default_factory=FerroHighlightSettings
    )
    spins_file_index: int = 0


@dataclass
class SpinvertData:
    """Parsed contents of a SPINVERT ``*_spins_NN.txt`` output file."""

    title: str
    cell_lengths: np.ndarray  # (3,) a, b, c in Angstrom
    cell_angles: np.ndarray  # (3,) alpha, beta, gamma in degrees
    unit_cell_sites: np.ndarray  # (n_sites, 3) fractional coordinates
    supercell_size: np.ndarray  # (3,) number of unit cells along a, b, c
    site_of_spin: np.ndarray  # (n_spins,) 0-indexed site id for each spin
    box_location: np.ndarray  # (n_spins, 3) unit-cell index of each spin
    spin_vectors: np.ndarray  # (n_spins, 3) spin direction vectors


# --------------------------------------------------------------------------- #
# File discovery and parsing
# --------------------------------------------------------------------------- #


def find_spins_file(data_dir: Path, index: int = 0) -> Path:
    """Return the ``index``-th ``*_spins_*`` file found in ``data_dir``."""
    candidates = sorted(p for p in data_dir.iterdir() if "_spins_" in p.name)
    if not candidates:
        raise FileNotFoundError(f"No '*_spins_*' file found in {data_dir}")
    return candidates[index]


def find_scf_file(data_dir: Path) -> Path | None:
    """Return the spin-correlation-function file in ``data_dir``, if any."""
    candidates = sorted(p for p in data_dir.iterdir() if p.name.endswith("scf.txt"))
    return candidates[0] if candidates else None


def parse_spinvert_file(path: Path) -> SpinvertData:
    """Parse a SPINVERT ``*_spins_NN.txt`` file into a :class:`SpinvertData`."""
    lines = path.read_text().splitlines()
    title = lines[0].replace("TITLE", "").replace(" ", "").strip()

    spin_line_indices = [i for i, line in enumerate(lines) if "SPIN" in line]
    if not spin_line_indices:
        raise ValueError(f"No SPIN records found in {path}")
    header_lines = spin_line_indices[0]

    site_of_spin, x_box, y_box, z_box, xv, yv, zv = np.genfromtxt(
        path, skip_header=header_lines, usecols=(1, 2, 3, 4, 5, 6, 7), unpack=True
    )
    total_sites = int(site_of_spin.max())

    box_location = np.stack((x_box, y_box, z_box), axis=1)
    spin_vectors = np.stack((xv, yv, zv), axis=1)

    cell_angles = np.genfromtxt(path, skip_header=1, usecols=(4, 5, 6), max_rows=1)
    cell_and_sites = np.genfromtxt(
        path, skip_header=1, usecols=(1, 2, 3), max_rows=total_sites + 2
    )
    cell_lengths = cell_and_sites[0]
    unit_cell_sites = cell_and_sites[1 : total_sites + 1]
    supercell_size = cell_and_sites[-1]

    return SpinvertData(
        title=title,
        cell_lengths=cell_lengths,
        cell_angles=cell_angles,
        unit_cell_sites=unit_cell_sites,
        supercell_size=supercell_size,
        site_of_spin=(site_of_spin.astype(int) - 1),
        box_location=box_location,
        spin_vectors=spin_vectors,
    )


# --------------------------------------------------------------------------- #
# Geometry
# --------------------------------------------------------------------------- #


def apply_symmetry_operations(
    fractional_positions: np.ndarray, operations: Sequence[SymmetryOp]
) -> np.ndarray:
    """Apply symmetry operators to a set of fractional positions.

    Parameters
    ----------
    fractional_positions:
        Array of shape ``(n_atoms, 3)``.
    operations:
        Symmetry operators to apply to every atom.

    Returns
    -------
    np.ndarray
        Array of shape ``(n_atoms, n_operations, 3)``, wrapped into ``[0, 1)``.
    """
    x, y, z = (
        fractional_positions[:, 0],
        fractional_positions[:, 1],
        fractional_positions[:, 2],
    )
    transformed = np.stack(
        [np.stack(op(x, y, z), axis=-1) for op in operations], axis=1
    )
    return transformed % 1.0


def magnetic_supercell_positions(
    data: SpinvertData,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute cartesian and fractional positions of every magnetic spin.

    Returns
    -------
    tuple
        ``(cartesian_positions, fractional_positions, supercell_box_lengths)``.
    """
    supercell_box = data.cell_lengths * data.supercell_size
    box_cartesian = (data.box_location / data.supercell_size) * supercell_box
    site_offsets = data.cell_lengths * data.unit_cell_sites

    cartesian = box_cartesian + site_offsets[data.site_of_spin]
    fractional = cartesian / supercell_box
    return cartesian, fractional, supercell_box


def non_magnetic_supercell_positions(
    non_magnetic_atoms: Sequence[NonMagneticAtom],
    symmetry_operations: Sequence[SymmetryOp],
    cell_lengths: np.ndarray,
    supercell_size: np.ndarray,
    supercell_box: np.ndarray,
) -> list[np.ndarray]:
    """Generate fractional supercell positions for each non-magnetic atom.

    Returns
    -------
    list[np.ndarray]
        One array per input atom, each of shape
        ``(n_symmetry_ops * n_unit_cells, 3)`` of fractional coordinates.
    """
    positions = np.array([atom.fractional_position for atom in non_magnetic_atoms])
    symmetry_frac = apply_symmetry_operations(positions, symmetry_operations)
    site_offsets = cell_lengths * symmetry_frac  # cartesian offset within unit cell

    box_indices = np.array(list(product(*(range(int(n)) for n in supercell_size))))
    box_origins = (box_indices / supercell_size) * supercell_box  # (n_cells, 3)

    per_atom_positions = []
    for atom_offsets in site_offsets:  # shape (n_ops, 3)
        cartesian = atom_offsets[:, None, :] + box_origins[None, :, :]
        per_atom_positions.append(cartesian.reshape(-1, 3) / supercell_box)
    return per_atom_positions


def classify_ferro_antiferro(
    magnetic_cartesian: np.ndarray,
    magnetic_atom: str,
    supercell_box: np.ndarray,
    r_distance: np.ndarray,
    mag_corr: np.ndarray,
    settings: FerroHighlightSettings,
) -> tuple[list[str], int]:
    """Label each magnetic atom by its correlation with the central atom.

    The atom closest to the geometric centre of the supercell is used as the
    reference. Every other magnetic atom is looked up in the spin-correlation
    function (``r_distance``/``mag_corr``) at its separation from that
    reference atom and labelled ``up_label``/``down_label`` accordingly, or
    left as ``magnetic_atom`` when the correlation is weak or the pair is
    further apart than the correlation function was measured.

    Returns
    -------
    tuple
        ``(labels, center_atom_index)``.
    """
    center_index = int(KDTree(magnetic_cartesian).query(supercell_box / 2)[1])
    center_position = magnetic_cartesian[center_index]

    distances = np.linalg.norm(magnetic_cartesian - center_position, axis=1)
    nearest_bin = np.abs(r_distance[None, :] - distances[:, None]).argmin(axis=1)
    correlations = mag_corr[nearest_bin]

    labels = []
    for distance, correlation in zip(distances, correlations, strict=True):
        if abs(correlation) < settings.correlation_cutoff or distance > r_distance[-1]:
            labels.append(magnetic_atom)
        elif correlation < 0:
            labels.append(settings.down_label)
        else:
            labels.append(settings.up_label)
    return labels, center_index


# --------------------------------------------------------------------------- #
# .cmtx writing
# --------------------------------------------------------------------------- #

_CMTX_HEADER_TEMPLATE = """\
! Lattice type
LATC  P

! Spacegroup symbol:  P 1
! Total of 1 general equivalent positions (excl. lattice operators)
SYMM     +x       +y       +z

! Plot range (min/max along x, y and z axes)
XYZR  0.000000 1.000000 0.000000 1.000000 0.000000 1.000000

! Model type
MODL  3

! Background colour
BKCL  1.000 1.000 1.000

! Bond colour
BNCL  0.6867 0.6867 0.6867

! Relative bond radii for ball-and-stick and stick plots
BRAD    0.2500   0.5000

! Illumination direction
LTDN  -0.500000 0.500000 0.707100

! Atom, bond, polyhedral and surface rendering coefficients
AREN  0.250000 0.750000 1.000000 30
BREN  0.500000 0.900000 1.000000 10
PREN  0.500000 0.900000 0.000000 1
SREN  0.500000 1.000000 0.000000 1

! Unit cell visibility (1=true; 0 = false)
SHCL  {show_cell}

! Orientation matrix: 11 12 13; 21 22 23; 31 32 33
! OMAT  4.000 0.000 -0.000  -0.000 -5.000 0.000  -0.000 -0.000 -6.000

! Asymmetric unit
ATOM
"""


def _atom_labels(n: int) -> list[str]:
    """One-letter labels (A, B, C, ...) used to disambiguate atom names."""
    if n > len(string.ascii_uppercase):
        raise ValueError("More than 26 non-magnetic atoms is not supported")
    return list(string.ascii_uppercase[:n])


def _write_non_magnetic_atoms(
    handle: TextIO,
    atoms: Sequence[NonMagneticAtom],
    fractional_positions: Sequence[np.ndarray],
) -> None:
    for atom, label, positions in zip(
        atoms, _atom_labels(len(atoms)), fractional_positions, strict=True
    ):
        for i, (x, y, z) in enumerate(positions):
            handle.write(
                f"{atom.element}    {atom.element}{label}{i}    {x}    {y}    {z}\n"
            )


def _write_nearby_non_magnetic_atoms(
    handle: TextIO,
    atoms: Sequence[NonMagneticAtom],
    fractional_positions: Sequence[np.ndarray],
    highlighted_cartesian: np.ndarray,
    supercell_box: np.ndarray,
    max_distance: float,
) -> None:
    """Write non-magnetic atoms that lie within ``max_distance`` of a
    highlighted magnetic atom. Each qualifying atom is written once (the
    original script could emit duplicates when close to several highlighted
    atoms; this fixes that)."""
    if highlighted_cartesian.size == 0:
        return
    for atom, label, positions in zip(
        atoms, _atom_labels(len(atoms)), fractional_positions, strict=True
    ):
        cartesian = positions * supercell_box
        for i, (frac, cart) in enumerate(zip(positions, cartesian, strict=True)):
            distances = np.linalg.norm(highlighted_cartesian - cart, axis=1)
            if distances.min() < max_distance:
                x, y, z = frac
                handle.write(
                    f"{atom.element}    {atom.element}{label}{i}    {x}    {y}    {z}\n"
                )


class CmtxWriter:
    """Writes CrystalMaker .cmtx files for a SPINVERT magnetic structure."""

    def __init__(self, data: SpinvertData, supercell_box: np.ndarray) -> None:
        self.data = data
        self.supercell_box = supercell_box

    def _write_title_and_cell(self, handle: TextIO) -> None:
        handle.write(f"TITl\t{self.data.title}\n")
        cell_values = [*self.supercell_box, *self.data.cell_angles]
        handle.write("CELL" + "".join(f"\t{v}" for v in cell_values) + "\n")

    def write_structure(
        self,
        path: Path,
        magnetic_atom: str,
        magnetic_fractional: np.ndarray,
        non_magnetic_atoms: Sequence[NonMagneticAtom],
        non_magnetic_fractional: Sequence[np.ndarray],
        spin_vectors: np.ndarray,
        vector_style: VectorStyle,
    ) -> None:
        """Write the full nuclear + magnetic structure .cmtx file."""
        with path.open("w") as handle:
            self._write_title_and_cell(handle)
            handle.write(_CMTX_HEADER_TEMPLATE.format(show_cell=1))

            for index, (x, y, z) in enumerate(magnetic_fractional):
                handle.write(
                    f"{magnetic_atom}         {magnetic_atom}{index}    {x}    {y}    {z}    \n"  # noqa
                )

            _write_non_magnetic_atoms(
                handle, non_magnetic_atoms, non_magnetic_fractional
            )

            handle.write(
                "! Atom Vector: apply vectors on a per-ATOM basis\n"
                "AVEC\n"
                "! <atom label>\t  <xFrac>  <yFrac>  <zFrac>\t<vecU> <vecV> <vecW> "
                "<length>  <red> <green> <blue>    <style>\n"
            )
            red, green, blue = vector_style.colour_rgb
            for index, ((x, y, z), (u, v, w)) in enumerate(
                zip(magnetic_fractional, spin_vectors, strict=True)
            ):
                handle.write(
                    f"{magnetic_atom}{index}     {x}    {y}    {z}    {u}    {v}    {w}  "  # noqa
                    f"{vector_style.bond_length} {red} {green} {blue} {vector_style.style}\n"  # noqa
                )

    def write_highlight(
        self,
        path: Path,
        magnetic_atom: str,
        magnetic_fractional: np.ndarray,
        spin_labels: Sequence[str],
        non_magnetic_atoms: Sequence[NonMagneticAtom],
        non_magnetic_fractional: Sequence[np.ndarray],
        highlight: FerroHighlightSettings,
        center_index: int,
    ) -> None:
        """Write a .cmtx file labelling each magnetic atom by correlation."""
        with path.open("w") as handle:
            self._write_title_and_cell(handle)
            handle.write(_CMTX_HEADER_TEMPLATE.format(show_cell=0))

            highlighted_fractional: list[tuple[float, float, float]] = []
            for index, (label, (x, y, z)) in enumerate(
                zip(spin_labels, magnetic_fractional, strict=True)
            ):
                if highlight.highlight_center_atom and index == center_index:
                    handle.write(
                        f"{magnetic_atom}         {magnetic_atom}{index}    {x}    {y}    {z}    \n"  # noqa
                    )
                if label != magnetic_atom:
                    handle.write(
                        f"{label}         {magnetic_atom}{index}    {x}    {y}    {z}    \n"  # noqa
                    )
                    highlighted_fractional.append((x, y, z))

            highlighted_cartesian = (
                np.asarray(highlighted_fractional) * self.supercell_box
                if highlighted_fractional
                else np.empty((0, 3))
            )
            _write_nearby_non_magnetic_atoms(
                handle,
                non_magnetic_atoms,
                non_magnetic_fractional,
                highlighted_cartesian,
                self.supercell_box,
                highlight.atom_distance,
            )


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


def convert_spinvert_to_cmtx(config: SpinvertConfig) -> None:
    """Run the full spins -> .cmtx conversion described by ``config``."""
    spins_path = find_spins_file(config.data_dir, config.spins_file_index)
    data = parse_spinvert_file(spins_path)

    magnetic_cartesian, magnetic_fractional, supercell_box = (
        magnetic_supercell_positions(data)
    )
    non_magnetic_fractional = non_magnetic_supercell_positions(
        config.non_magnetic_atoms,
        config.symmetry_operations,
        data.cell_lengths,
        data.supercell_size,
        supercell_box,
    )

    vector_style = config.vector_style.resolved(config.magnetic_atom)

    writer = CmtxWriter(data, supercell_box)
    structure_path = config.data_dir / f"{data.title}_spinvert.cmtx"
    writer.write_structure(
        structure_path,
        config.magnetic_atom,
        magnetic_fractional,
        config.non_magnetic_atoms,
        non_magnetic_fractional,
        data.spin_vectors,
        vector_style,
    )
    logger.info("Wrote %s", structure_path)

    if config.ferro_highlight.enabled:
        scf_path = find_scf_file(config.data_dir)
        if scf_path is None:
            logger.warning(
                "No '*scf.txt' file found in %s; run spindist first. "
                "Skipping ferro highlighting.",
                config.data_dir,
            )
        else:
            r_distance, mag_corr, _ = np.genfromtxt(
                scf_path, usecols=(0, 1, 2), unpack=True
            )
            labels, center_index = classify_ferro_antiferro(
                magnetic_cartesian,
                config.magnetic_atom,
                supercell_box,
                r_distance,
                mag_corr,
                config.ferro_highlight,
            )
            logger.info(
                "Correlation cutoff = %s", config.ferro_highlight.correlation_cutoff
            )

            highlight_path = (
                config.data_dir / f"{data.title}_spinvert_AFM_highlight.cmtx"
            )
            writer.write_highlight(
                highlight_path,
                config.magnetic_atom,
                magnetic_fractional,
                labels,
                config.non_magnetic_atoms,
                non_magnetic_fractional,
                config.ferro_highlight,
                center_index,
            )
            logger.info("Wrote %s", highlight_path)

    logger.info("spins to .cmtx conversion complete")


def main() -> None:
    """Entry point. Edit the ``SpinvertConfig`` below for your own dataset."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    config = SpinvertConfig(
        data_dir=Path(
            "/Users/ssrix/data/spinvert/spinvert_calc/LnOHCO3/finerebin_TbODCO3/"
            "Ising/TbODCO3_1-46K"
        ),
        magnetic_atom="Tb",
        non_magnetic_atoms=[
            NonMagneticAtom("O", (0.001, -0.2051, 0.1132)),
            NonMagneticAtom("O", (0.28281, 0.4006, 0.1023)),
            NonMagneticAtom("O", (-0.259, 0.4101, 0.1122)),
            NonMagneticAtom("O", (0.5088, 0.0488, 0.2007)),
            NonMagneticAtom("C", (0.502, 0.4500, 0.1734)),
            NonMagneticAtom("D", (-0.10, -0.28, 0.04)),
        ],
        # bond_length left as None: derived from the magnetic atom's covalent
        # radius via mendeleev. Pass an explicit float here to override it.
        vector_style=VectorStyle(colour_rgb=(0.0, 0.0, 1.0), style=3),
        ferro_highlight=FerroHighlightSettings(
            enabled=True,
            correlation_cutoff=0.04,
            atom_distance=3.0,
            highlight_center_atom=False,
        ),
        spins_file_index=0,
    )

    convert_spinvert_to_cmtx(config)


if __name__ == "__main__":
    main()
