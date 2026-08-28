"""Helpers for locating and parsing Spinvert's plain-text I/O files.

Spinvert reads ``[title]_data.txt`` and ``[title]_config.txt`` from the
working directory, and periodically (re)writes numbered output files as
refinement proceeds:

    [title]_fit_01.txt, [title]_fit_02.txt, ...   -- current fit: two columns,
                                                      Q and calculated intensity
    [title]_chi_01.txt, [title]_chi_02.txt, ...   -- chi^2 vs proposed moves
                                                      per spin

Later runs get higher numbers; the highest-numbered file is always the
most recent.
"""

import re
from pathlib import Path

import numpy as np

_NUMBERED_FILE_RE = "^{title}_{kind}_(\\d+)\\.txt$"


def data_file_path(workdir: Path, title: str) -> Path:
    return workdir / f"{title}_data.txt"


def config_file_path(workdir: Path, title: str) -> Path:
    return workdir / f"{title}_config.txt"


def discover_titles(workdir: Path) -> list[str]:
    """Return titles for every ``[title]_data.txt`` found in workdir."""
    if not workdir.is_dir():
        return []
    titles = sorted(p.name[: -len("_data.txt")] for p in workdir.glob("*_data.txt"))
    return titles


def find_latest_numbered_file(workdir: Path, title: str, kind: str) -> Path | None:
    """Find the highest-numbered ``[title]_{kind}_NN.txt`` file in workdir.

    kind is typically "fit" or "chi".
    """
    if not workdir.is_dir():
        return None

    pattern = re.compile(_NUMBERED_FILE_RE.format(title=re.escape(title), kind=kind))
    best: tuple[int, Path] | None = None
    for path in workdir.iterdir():
        match = pattern.match(path.name)
        if not match:
            continue
        run_number = int(match.group(1))
        if best is None or run_number > best[0]:
            best = (run_number, path)
    return best[1] if best else None


def generated_output_files(workdir: Path, title: str) -> list[Path]:
    """Every file spinvert writes for ``title``: the numbered chi/fit/spins
    files plus ``[title]_form_fac_sq.txt``. Input files (``_data.txt`` /
    ``_config.txt``) are never included. Returns existing files, sorted.
    """
    if not workdir.is_dir():
        return []

    numbered = re.compile(r"^" + re.escape(title) + r"_(?:chi|fit|spins)_\d+\.txt$")
    form_factor = f"{title}_form_fac_sq.txt"
    return sorted(
        path
        for path in workdir.iterdir()
        if path.is_file() and (numbered.match(path.name) or path.name == form_factor)
    )


def parse_xy_columns(path: Path, ncols: int) -> list[np.ndarray]:
    """Parse a whitespace- or comma-delimited numeric file with at least
    ncols columns, skipping blank/comment/header lines that don't parse
    as numbers. Returns a list of ncols 1-D arrays.
    """
    rows: list[list[float]] = []
    text = path.read_text()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", "!")):
            continue
        tokens = line.split(",") if "," in line else line.split()
        if len(tokens) < ncols:
            continue
        try:
            values = [float(tok) for tok in tokens[:ncols]]
        except ValueError:
            continue
        rows.append(values)

    if not rows:
        return [np.array([]) for _ in range(ncols)]

    data = np.array(rows, dtype=float)
    return [data[:, i] for i in range(ncols)]


def parse_data_file(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Parse a [title]_data.txt file: q, intensity, error (three columns)."""
    q, intensity, error = parse_xy_columns(path, 3)
    return q, intensity, error


def parse_fit_file(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Parse a [title]_fit_NN.txt file: q, calculated intensity (two columns)."""
    q, intensity = parse_xy_columns(path, 2)
    return q, intensity


def parse_chi_file(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Parse a [title]_chi_NN.txt file: moves per spin, chi^2."""
    moves, chi2 = parse_xy_columns(path, 2)
    return moves, chi2
