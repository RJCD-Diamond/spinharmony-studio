"""Tests for :mod:`spinharmony_studio.spins_to_cmtx`."""

from unittest.mock import patch

import numpy as np
import pytest

from spinharmony_studio.spins_to_cmtx import (
    AtomRenderStyle,
    BondMaxSpec,
    CmtxRenderSettings,
    CmtxWriter,
    FerroHighlightSettings,
    NonMagneticAtom,
    SpinvertConfig,
    VectorStyle,
    _atom_labels,
    _cutoff_suffix,
    apply_symmetry_operations,
    bond_length_from_element,
    classify_ferro_antiferro,
    convert_spinvert_to_cmtx,
    default_symmetry_operations,
    find_scf_file,
    find_spins_file,
    magnetic_supercell_positions,
    main,
    non_magnetic_supercell_positions,
    parse_spinvert_file,
)

_SIMPLE_SPINS_FILE = """\
TITLE Test
CELL 5.0 5.0 5.0 90.0 90.0 90.0
SITE 0.0 0.0 0.0
BOX 1 1 1
SPIN 1 0 0 0 0.0 0.0 1.0
SPIN 1 0 0 0 0.0 0.0 -1.0
"""

_TWO_SITE_SPINS_FILE = """\
TITLE Two
CELL 4.0 4.0 4.0 90.0 90.0 90.0
SITE 0.0 0.0 0.0
SITE 0.5 0.5 0.5
BOX 2 1 1
SPIN 1 0 0 0 1.0 0.0 0.0
SPIN 2 0 0 0 -1.0 0.0 0.0
SPIN 1 1 0 0 1.0 0.0 0.0
SPIN 2 1 0 0 -1.0 0.0 0.0
"""

_SIMPLE_RENDER = CmtxRenderSettings(
    bond_specs=[BondMaxSpec("Tb", "O", 2.5)],
    atom_styles=[AtomRenderStyle("Tb", radius=1.0, colour_rgb=(1.0, 0.0, 0.0))],
)


def test_returns_four_operations():
    assert len(default_symmetry_operations()) == 4


def test_first_operation_is_identity():
    identity = default_symmetry_operations()[0]
    x, y, z = np.array([0.2]), np.array([0.3]), np.array([0.4])
    result = identity(x, y, z)
    np.testing.assert_allclose(result, (x, y, z))


def test_known_element_returns_positive_length():
    assert bond_length_from_element("Fe") > 0


def test_unknown_element_falls_back():
    assert bond_length_from_element("NotAnElement") == 1.5


def test_resolved_keeps_explicit_bond_length():
    style = VectorStyle(bond_length=2.0)
    assert style.resolved("Tb") is style


def test_resolved_derives_bond_length_when_unset():
    style = VectorStyle()
    with patch(
        "spinharmony_studio.spins_to_cmtx.bond_length_from_element",
        return_value=1.23,
    ):
        resolved = style.resolved("Tb")
    assert resolved.bond_length == 1.23
    assert resolved is not style


def test_bond_max_spec_to_line():
    spec = BondMaxSpec("C", "O", 2.501)
    assert spec.to_line() == "BMAX  C   O   2.501"


def test_atom_render_style_to_line():
    style = AtomRenderStyle("Tb", radius=1.18, colour_rgb=(0.443, 0.017, 0.998))
    line = style.to_line()
    assert line.startswith("Tb")
    assert "1.18" in line


def test_find_spins_file_returns_sorted_match(tmp_path):
    (tmp_path / "Foo_spins_02.txt").write_text("")
    (tmp_path / "Foo_spins_01.txt").write_text("")
    (tmp_path / "unrelated.txt").write_text("")
    result = find_spins_file(tmp_path)
    assert result.name == "Foo_spins_01.txt"


def test_find_spins_file_index(tmp_path):
    (tmp_path / "Foo_spins_01.txt").write_text("")
    (tmp_path / "Foo_spins_02.txt").write_text("")
    result = find_spins_file(tmp_path, index=1)
    assert result.name == "Foo_spins_02.txt"


def test_find_spins_file_raises_when_none_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        find_spins_file(tmp_path)


def test_find_scf_file_found(tmp_path):
    (tmp_path / "Foo_scf.txt").write_text("")
    result = find_scf_file(tmp_path)
    assert result is not None
    assert result.name == "Foo_scf.txt"


def test_find_scf_file_none_when_absent(tmp_path):
    assert find_scf_file(tmp_path) is None


def test_parses_minimal_file(tmp_path):
    path = tmp_path / "Test_spins_01.txt"
    path.write_text(_SIMPLE_SPINS_FILE)
    data = parse_spinvert_file(path)
    assert data.title == "Test"
    np.testing.assert_allclose(data.cell_lengths, [5.0, 5.0, 5.0])
    np.testing.assert_allclose(data.cell_angles, [90.0, 90.0, 90.0])
    np.testing.assert_allclose(data.unit_cell_sites, [[0.0, 0.0, 0.0]])
    np.testing.assert_allclose(data.supercell_size, [1.0, 1.0, 1.0])
    np.testing.assert_array_equal(data.site_of_spin, [0, 0])
    np.testing.assert_allclose(data.spin_vectors, [[0, 0, 1], [0, 0, -1]])


def test_title_with_internal_spaces_is_stripped_entirely(tmp_path):
    # Matches the parser's actual (somewhat surprising) behaviour: it
    # strips ALL whitespace from the title line, not just the edges.
    text = _SIMPLE_SPINS_FILE.replace("TITLE Test", "TITLE My Compound")
    path = tmp_path / "spins_01.txt"
    path.write_text(text)
    data = parse_spinvert_file(path)
    assert data.title == "MyCompound"


def test_no_spin_lines_raises(tmp_path):
    path = tmp_path / "spins_01.txt"
    path.write_text("TITLE Test\nCELL 1 1 1 90 90 90\n")
    with pytest.raises(ValueError, match="No SPIN records"):
        parse_spinvert_file(path)


def test_apply_symmetry_operations_identity_wraps_to_unit_cell():
    positions = np.array([[1.2, -0.3, 0.5]])
    result = apply_symmetry_operations(positions, [lambda x, y, z: (x, y, z)])
    np.testing.assert_allclose(result[0, 0], [0.2, 0.7, 0.5], atol=1e-10)


def test_apply_symmetry_operations_shape():
    positions = np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
    ops = default_symmetry_operations()
    result = apply_symmetry_operations(positions, ops)
    assert result.shape == (2, 4, 3)


def test_magnetic_supercell_positions_single_site_at_origin(tmp_path):
    path = tmp_path / "spins_01.txt"
    path.write_text(_SIMPLE_SPINS_FILE)
    data = parse_spinvert_file(path)
    cartesian, fractional, supercell_box = magnetic_supercell_positions(data)
    np.testing.assert_allclose(cartesian, [[0, 0, 0], [0, 0, 0]])
    np.testing.assert_allclose(supercell_box, [5.0, 5.0, 5.0])


def test_magnetic_supercell_positions_two_sites_two_boxes(tmp_path):
    path = tmp_path / "spins_01.txt"
    path.write_text(_TWO_SITE_SPINS_FILE)
    data = parse_spinvert_file(path)
    cartesian, fractional, supercell_box = magnetic_supercell_positions(data)
    # supercell_box = cell_lengths * supercell_size = 4 * (2,1,1) = (8,4,4)
    np.testing.assert_allclose(supercell_box, [8.0, 4.0, 4.0])
    assert cartesian.shape == (4, 3)
    assert fractional.shape == (4, 3)


def test_non_magnetic_supercell_positions_single_cell_identity():
    atoms = [NonMagneticAtom("O", (0.1, 0.2, 0.3))]
    positions = non_magnetic_supercell_positions(
        atoms,
        [lambda x, y, z: (x, y, z)],
        cell_lengths=np.array([5.0, 5.0, 5.0]),
        supercell_size=np.array([1, 1, 1]),
        supercell_box=np.array([5.0, 5.0, 5.0]),
    )
    assert len(positions) == 1
    np.testing.assert_allclose(positions[0], [[0.1, 0.2, 0.3]])


def test_labels_up_down_and_base():
    # supercell_box/2 = (1, 0, 0) sits exactly on atom 0, so it's the
    # unambiguous center; the others are at increasing distance from it.
    magnetic_cartesian = np.array(
        [[1.0, 0.0, 0.0], [2.0, 0.0, 0.0], [3.0, 0.0, 0.0], [100.0, 0.0, 0.0]]
    )
    supercell_box = np.array([2.0, 0.0, 0.0])
    r_distance = np.array([0.0, 1.0, 2.0])
    mag_corr = np.array([1.0, 0.8, -0.8])
    settings = FerroHighlightSettings(correlation_cutoff=0.05)

    labels, center_index = classify_ferro_antiferro(
        magnetic_cartesian, "Tb", supercell_box, r_distance, mag_corr, settings
    )
    assert center_index == 0
    # The center atom is not special-cased: its self-correlation (r=0,
    # corr=1.0) labels it the same as any other strongly-correlated atom.
    assert labels[0] == settings.up_label
    assert labels[1] == settings.up_label  # distance 1, corr=0.8>0
    assert labels[2] == settings.down_label  # distance 2, corr=-0.8<0
    assert labels[3] == "Tb"  # far beyond r_distance range -> base label


def test_weak_correlation_falls_back_to_base_label():
    magnetic_cartesian = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    supercell_box = np.array([0.0, 0.0, 0.0])
    r_distance = np.array([0.0, 1.0])
    mag_corr = np.array([1.0, 0.01])
    settings = FerroHighlightSettings(correlation_cutoff=0.05)
    labels, _ = classify_ferro_antiferro(
        magnetic_cartesian, "Tb", supercell_box, r_distance, mag_corr, settings
    )
    assert labels[1] == "Tb"


def test_atom_labels_basic():
    assert _atom_labels(3) == ["AA", "AB", "AC"]


def test_atom_labels_too_many_raises():
    with pytest.raises(ValueError, match="Too many"):
        _atom_labels(27 * 26 + 1)


def test_cutoff_suffix_formats_decimal():
    assert _cutoff_suffix(0.05) == "0-05"


def _data_and_writer(tmp_path):
    path = tmp_path / "spins_01.txt"
    path.write_text(_SIMPLE_SPINS_FILE)
    data = parse_spinvert_file(path)
    _, fractional, supercell_box = magnetic_supercell_positions(data)
    writer = CmtxWriter(data, supercell_box)
    return data, fractional, writer


def test_write_structure_produces_file_with_expected_sections(tmp_path):
    data, fractional, writer = _data_and_writer(tmp_path)
    out = tmp_path / "out.cmtx"
    vector_style = VectorStyle(bond_length=1.5)
    writer.write_structure(
        out,
        "Tb",
        fractional,
        [],
        [],
        data.spin_vectors,
        vector_style,
        _SIMPLE_RENDER,
    )
    text = out.read_text()
    assert "TITl\tTest" in text
    assert "AVEC" in text
    assert "Tb0" in text
    assert "Tb1" in text


def test_write_structure_includes_non_magnetic_atoms(tmp_path):
    data, fractional, writer = _data_and_writer(tmp_path)
    out = tmp_path / "out.cmtx"
    atoms = [NonMagneticAtom("O", (0.1, 0.1, 0.1))]
    non_mag_fractional = non_magnetic_supercell_positions(
        atoms,
        [lambda x, y, z: (x, y, z)],
        data.cell_lengths,
        data.supercell_size,
        np.array([5.0, 5.0, 5.0]),
    )
    writer.write_structure(
        out,
        "Tb",
        fractional,
        atoms,
        non_mag_fractional,
        data.spin_vectors,
        VectorStyle(bond_length=1.0),
        _SIMPLE_RENDER,
    )
    assert "OAA0" in out.read_text()


def test_write_highlight_labels_and_center_atom(tmp_path):
    data, fractional, writer = _data_and_writer(tmp_path)
    out = tmp_path / "highlight.cmtx"
    highlight = FerroHighlightSettings(highlight_center_atom=True)
    writer.write_highlight(
        out,
        "Tb",
        fractional,
        ["Up", "Tb"],
        [],
        [],
        highlight,
        center_index=1,
        render=_SIMPLE_RENDER,
    )
    text = out.read_text()
    assert "Up         Tb0" in text
    # center atom (index 1) written with its base label since highlighted
    assert "Tb         Tb1" in text


def test_write_highlight_includes_nearby_non_magnetic_atoms(tmp_path):
    data, fractional, writer = _data_and_writer(tmp_path)
    out = tmp_path / "highlight.cmtx"
    atoms = [NonMagneticAtom("O", (0.0, 0.0, 0.0))]
    non_mag_fractional = non_magnetic_supercell_positions(
        atoms,
        [lambda x, y, z: (x, y, z)],
        data.cell_lengths,
        data.supercell_size,
        np.array([5.0, 5.0, 5.0]),
    )
    highlight = FerroHighlightSettings(atom_distance=10.0)
    writer.write_highlight(
        out,
        "Tb",
        fractional,
        ["Up", "Dw"],
        atoms,
        non_mag_fractional,
        highlight,
        center_index=0,
        render=_SIMPLE_RENDER,
    )
    assert "OAA0" in out.read_text()


def test_write_highlight_with_no_highlighted_atoms(tmp_path):
    data, fractional, writer = _data_and_writer(tmp_path)
    out = tmp_path / "highlight.cmtx"
    highlight = FerroHighlightSettings()
    writer.write_highlight(
        out, "Tb", fractional, ["Tb", "Tb"], [], [], highlight, 0, _SIMPLE_RENDER
    )
    assert out.read_text()  # wrote something without error


def _config(tmp_path, **overrides):
    # non_magnetic_atoms deliberately non-empty: non_magnetic_supercell_
    # positions() builds np.array([atom.fractional_position for atom in
    # non_magnetic_atoms]), which is 1-D (not (0, 3)) when the list is
    # empty, and apply_symmetry_operations' [:, 0] indexing then raises.
    kwargs = {
        "data_dir": tmp_path,
        "magnetic_atom": "Tb",
        "non_magnetic_atoms": [NonMagneticAtom("O", (0.2, 0.2, 0.2))],
        "structure_render": _SIMPLE_RENDER,
        "highlight_render": _SIMPLE_RENDER,
        "vector_style": VectorStyle(bond_length=1.0),
    }
    kwargs.update(overrides)
    return SpinvertConfig(**kwargs)


def test_writes_structure_file_without_scf(tmp_path):
    (tmp_path / "Test_spins_01.txt").write_text(_SIMPLE_SPINS_FILE)
    convert_spinvert_to_cmtx(_config(tmp_path))
    assert (tmp_path / "Test_spinvert.cmtx").is_file()
    assert not list(tmp_path.glob("*highlight*"))


def test_writes_highlight_file_with_scf(tmp_path):
    (tmp_path / "Test_spins_01.txt").write_text(_SIMPLE_SPINS_FILE)
    (tmp_path / "Test_scf.txt").write_text("0.0 1.0 0\n1.0 -0.9 0\n2.0 0.9 0\n")
    highlight = FerroHighlightSettings(correlation_cutoff=0.05)
    convert_spinvert_to_cmtx(_config(tmp_path, ferro_highlight=highlight))
    assert (tmp_path / "Test_spinvert.cmtx").is_file()
    assert list(tmp_path.glob("*highlight*"))


def test_ferro_highlight_disabled_skips_scf_lookup(tmp_path):
    (tmp_path / "Test_spins_01.txt").write_text(_SIMPLE_SPINS_FILE)
    (tmp_path / "Test_scf.txt").write_text("0.0 1.0 0\n")
    config = _config(tmp_path, ferro_highlight=FerroHighlightSettings(enabled=False))
    convert_spinvert_to_cmtx(config)
    assert not list(tmp_path.glob("*highlight*"))


def test_main_builds_config_and_delegates(tmp_path):
    with patch(
        "spinharmony_studio.spins_to_cmtx.convert_spinvert_to_cmtx"
    ) as mock_convert:
        main()
    assert mock_convert.called
    (config,) = mock_convert.call_args.args
    assert config.magnetic_atom == "Tb"
