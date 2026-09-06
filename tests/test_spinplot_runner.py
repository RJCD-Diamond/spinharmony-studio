"""Tests for :mod:`spinharmony_studio.spinplot.spinplot_runner`.

This script only works for Heisenberg (SPIN_DIMENSION=3) spinvert output; it
assumes a fixed 19-line header before the first SPIN line (matching a 4-site
config, which is what the fixture below reproduces), reads spindist/spinplot
paths from settings, and drives both external programs via os.system.
"""

import os
from unittest.mock import patch

import pytest

from spinharmony_studio.spinplot import spinplot_runner
from spinharmony_studio.spinplot.spinplot_runner import spinplot_auto

_HEISENBERG_CONFIG = """\
TITLE Test
CELL 5.0 5.0 5.0 90.0 90.0 90.0
SITE 0.0 0.0 0.0
SITE 0.5 0.0 0.0
SITE 0.0 0.5 0.0
SITE 0.0 0.0 0.5
SPIN_DIMENSION 3
FORM_FACTOR_J0 1 1 1 1 1 1 1
WEIGHT 1
MOVES 300
BOX 5 5 5
SCALE REFINE
"""

_ISING_CONFIG = """\
TITLE Test
CELL 5.0 5.0 5.0 90.0 90.0 90.0
SITE 0.0 0.0 0.0
ANISOTROPY 0.0 0.0 1.0
SPIN_DIMENSION 1
FORM_FACTOR_J0 1 1 1 1 1 1 1
WEIGHT 1
MOVES 300
BOX 5 5 5
SCALE REFINE
"""

# Exactly 19 header lines (matching a 4-SITE config) before the first SPIN
# line, since spinplot_auto hardcodes skip_header=19.
_HEADER_19_LINES = [
    " TITLE Test",
    " CELL 5.0 5.0 5.0 90.0 90.0 90.0",
    " SITE 0.0 0.0 0.0",
    " SITE 0.5 0.0 0.0",
    " SITE 0.0 0.5 0.0",
    " SITE 0.0 0.0 0.5",
    " BOX 2 2 2",
    " FORM_FACTOR_J0 1 1 1 1 1 1 1",
    " FORM_FACTOR_J2 1 1 1 1 1 1 1",
    " C2 0.0",
    " PROPOSED_MOVES 100",
    " ACCEPTED_MOVES 50",
    " WEIGHT 1.0",
    " TEMP_SUBTRACT",
    " CHI_SQUARED 1.0",
    " R_FACTOR 1.0",
    " SCALE 1.0",
    " FLAT_BACKGROUND 0.0",
    " LINEAR_BACKGROUND 0.0",
]


def _spin_line(idx, box, spin):
    return f" SPIN {idx} {box[0]} {box[1]} {box[2]} {spin[0]} {spin[1]} {spin[2]}"


def _make_spins_file(path, spins):
    lines = list(_HEADER_19_LINES)
    for i, spin in enumerate(spins):
        lines.append(_spin_line((i % 4) + 1, (0, 0, 0), spin))
    path.write_text("\n".join(lines) + "\n")


def _setup_data_dir(tmp_path, config_text=_HEISENBERG_CONFIG, n_boxes=2):
    (tmp_path / "Test_config.txt").write_text(config_text)
    (tmp_path / "Test_data.txt").write_text("1.0 2.0 0.1\n")
    for n in range(1, n_boxes + 1):
        _make_spins_file(
            tmp_path / f"Test_spins_{n:02d}.txt",
            [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (0.0, 0.0, -1.0)],
        )
    return tmp_path


def _patched_paths(spindist="/fake/spindist", spinplot="/fake/spinplot"):
    return (
        patch.object(spinplot_runner, "load_spindist_path", lambda: spindist),
        patch.object(spinplot_runner, "load_spinplot_path", lambda: spinplot),
    )


def test_non_heisenberg_config_raises(tmp_path):
    (tmp_path / "Test_config.txt").write_text(_ISING_CONFIG)
    (tmp_path / "Test_data.txt").write_text("")
    with pytest.raises(ValueError, match="Heisenberg"):
        spinplot_auto(str(tmp_path))


def test_missing_executables_raises(tmp_path):
    _setup_data_dir(tmp_path)
    with (
        patch.object(spinplot_runner, "load_spindist_path", lambda: None),
        patch.object(spinplot_runner, "load_spinplot_path", lambda: "/fake/spinplot"),
    ):
        with pytest.raises(FileNotFoundError, match="spindist"):
            spinplot_auto(str(tmp_path))


def test_full_run_writes_expected_files_and_calls_os_system(tmp_path):
    _setup_data_dir(tmp_path)
    calls = []
    original_cwd = os.getcwd()
    load_spindist, load_spinplot = _patched_paths()
    try:
        with (
            load_spindist,
            load_spinplot,
            patch.object(
                spinplot_runner.os,
                "system",
                side_effect=lambda cmd: calls.append(cmd) or 0,
            ),
        ):
            spinplot_auto(str(tmp_path))
    finally:
        os.chdir(original_cwd)

    # Per-box conversion files were written.
    assert (tmp_path / "Test_01_spinplot.txt").is_file()
    assert (tmp_path / "Test_02_spinplot.txt").is_file()

    # The spindist input file lists both boxes plus the standard params.
    spindist_input = (tmp_path / "input_spindist.txt").read_text()
    assert "2" in spindist_input.splitlines()[0]
    assert "Test_01_spinplot.txt" in spindist_input
    assert "Test_spindist.txt" in spindist_input

    # spinplot input files for origin/top/bottom were written.
    assert (tmp_path / "input_spinplot_origin.txt").is_file()
    assert (tmp_path / "input_spinplot_top.txt").is_file()
    assert (tmp_path / "input_spinplot_bottom.txt").is_file()

    # os.system was invoked for spindist, 3x spinplot, and convert.
    assert any("fake/spindist" in c for c in calls)
    assert sum("fake/spinplot" in c for c in calls) == 3
    assert any("convert" in c for c in calls)


def test_double_digit_box_numbering(tmp_path):
    _setup_data_dir(tmp_path, n_boxes=11)
    original_cwd = os.getcwd()
    load_spindist, load_spinplot = _patched_paths()
    try:
        with (
            load_spindist,
            load_spinplot,
            patch.object(spinplot_runner.os, "system", return_value=0),
        ):
            spinplot_auto(str(tmp_path))
    finally:
        os.chdir(original_cwd)
    spindist_input = (tmp_path / "input_spindist.txt").read_text()
    assert "Test_01_spinplot.txt" in spindist_input
    assert "Test_11_spinplot.txt" in spindist_input


def test_gif_assembly_error_is_caught_and_logged(tmp_path, capsys):
    _setup_data_dir(tmp_path, n_boxes=1)

    def fake_system(cmd):
        if "convert" in cmd:
            raise RuntimeError("no convert binary")
        return 0

    original_cwd = os.getcwd()
    load_spindist, load_spinplot = _patched_paths()
    try:
        with (
            load_spindist,
            load_spinplot,
            patch.object(spinplot_runner.os, "system", side_effect=fake_system),
        ):
            spinplot_auto(str(tmp_path))
    finally:
        os.chdir(original_cwd)

    assert "Error occurred while creating GIF" in capsys.readouterr().out


def test_custom_nphi_ntheta_written_to_input(tmp_path):
    _setup_data_dir(tmp_path, n_boxes=1)
    original_cwd = os.getcwd()
    load_spindist, load_spinplot = _patched_paths()
    try:
        with (
            load_spindist,
            load_spinplot,
            patch.object(spinplot_runner.os, "system", return_value=0),
        ):
            spinplot_auto(str(tmp_path), nphi=20, ntheta=10)
    finally:
        os.chdir(original_cwd)
    lines = (tmp_path / "input_spindist.txt").read_text().splitlines()
    assert "20" in lines
    assert "10" in lines
