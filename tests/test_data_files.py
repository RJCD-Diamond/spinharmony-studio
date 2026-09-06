"""Tests for :mod:`spinharmony_studio.spinvert.gui.data_files`."""

import numpy as np

from spinharmony_studio.spinvert.gui.data_files import (
    config_file_path,
    data_file_path,
    discover_titles,
    find_latest_numbered_file,
    generated_output_files,
    parse_chi_file,
    parse_data_file,
    parse_fit_file,
    parse_scf_file,
    parse_xy_columns,
    plot_image_path,
    scf_file_path,
    scf_image_path,
)


def test_data_file_path(tmp_path):
    assert data_file_path(tmp_path, "Foo") == tmp_path / "Foo_data.txt"


def test_config_file_path(tmp_path):
    assert config_file_path(tmp_path, "Foo") == tmp_path / "Foo_config.txt"


def test_scf_file_path(tmp_path):
    assert scf_file_path(tmp_path, "Foo") == tmp_path / "Foo_scf.txt"


def test_plot_image_path(tmp_path):
    assert plot_image_path(tmp_path, "Foo") == tmp_path / "Foo_plot.png"


def test_scf_image_path(tmp_path):
    assert scf_image_path(tmp_path, "Foo") == tmp_path / "Foo_scf.png"


def test_finds_data_file_titles(tmp_path):
    (tmp_path / "Foo_data.txt").write_text("")
    (tmp_path / "Bar_data.txt").write_text("")
    (tmp_path / "unrelated.txt").write_text("")
    assert discover_titles(tmp_path) == ["Bar", "Foo"]


def test_discover_titles_missing_directory_returns_empty(tmp_path):
    assert discover_titles(tmp_path / "nope") == []


def test_no_data_files_returns_empty(tmp_path):
    assert discover_titles(tmp_path) == []


def test_finds_highest_numbered(tmp_path):
    (tmp_path / "Foo_fit_01.txt").write_text("")
    (tmp_path / "Foo_fit_10.txt").write_text("")
    (tmp_path / "Foo_fit_02.txt").write_text("")
    result = find_latest_numbered_file(tmp_path, "Foo", "fit")
    assert result is not None
    assert result.name == "Foo_fit_10.txt"


def test_ignores_other_titles_and_kinds(tmp_path):
    (tmp_path / "Foo_fit_01.txt").write_text("")
    (tmp_path / "Bar_fit_99.txt").write_text("")
    (tmp_path / "Foo_chi_99.txt").write_text("")
    result = find_latest_numbered_file(tmp_path, "Foo", "fit")
    assert result is not None
    assert result.name == "Foo_fit_01.txt"


def test_missing_directory_returns_none(tmp_path):
    assert find_latest_numbered_file(tmp_path / "nope", "Foo", "fit") is None


def test_no_match_returns_none(tmp_path):
    assert find_latest_numbered_file(tmp_path, "Foo", "fit") is None


def test_collects_numbered_and_extra_files(tmp_path):
    names = [
        "Foo_chi_01.txt",
        "Foo_fit_01.txt",
        "Foo_spins_01.txt",
        "Foo_form_fac_sq.txt",
        "Foo_scf.txt",
        "Foo_plot.png",
        "Foo_scf.png",
    ]
    for name in names:
        (tmp_path / name).write_text("")
    (tmp_path / "Foo_data.txt").write_text("")
    (tmp_path / "Foo_config.txt").write_text("")
    result = [p.name for p in generated_output_files(tmp_path, "Foo")]
    assert sorted(result) == sorted(names)


def test_excludes_other_titles(tmp_path):
    (tmp_path / "Foo_chi_01.txt").write_text("")
    (tmp_path / "Bar_chi_01.txt").write_text("")
    result = [p.name for p in generated_output_files(tmp_path, "Foo")]
    assert result == ["Foo_chi_01.txt"]


def test_generated_output_files_missing_directory_returns_empty(tmp_path):
    assert generated_output_files(tmp_path / "nope", "Foo") == []


def test_no_matches_returns_empty(tmp_path):
    assert generated_output_files(tmp_path, "Foo") == []


def test_parses_whitespace_delimited(tmp_path):
    path = tmp_path / "data.txt"
    path.write_text("1.0 2.0\n3.0 4.0\n")
    cols = parse_xy_columns(path, 2)
    np.testing.assert_allclose(cols[0], [1.0, 3.0])
    np.testing.assert_allclose(cols[1], [2.0, 4.0])


def test_parses_comma_delimited(tmp_path):
    path = tmp_path / "data.txt"
    path.write_text("1.0,2.0\n3.0,4.0\n")
    cols = parse_xy_columns(path, 2)
    np.testing.assert_allclose(cols[0], [1.0, 3.0])


def test_skips_blank_and_comment_lines(tmp_path):
    path = tmp_path / "data.txt"
    path.write_text("# header\n\n1.0 2.0\n! comment\n3.0 4.0\n")
    cols = parse_xy_columns(path, 2)
    assert len(cols[0]) == 2


def test_skips_lines_with_too_few_columns(tmp_path):
    path = tmp_path / "data.txt"
    path.write_text("1.0\n1.0 2.0\n")
    cols = parse_xy_columns(path, 2)
    assert len(cols[0]) == 1


def test_skips_unparseable_lines(tmp_path):
    path = tmp_path / "data.txt"
    path.write_text("not numbers here\n1.0 2.0\n")
    cols = parse_xy_columns(path, 2)
    assert len(cols[0]) == 1


def test_no_valid_rows_returns_empty_arrays(tmp_path):
    path = tmp_path / "data.txt"
    path.write_text("# nothing useful\n")
    cols = parse_xy_columns(path, 3)
    assert len(cols) == 3
    assert all(len(c) == 0 for c in cols)


def test_extra_columns_ignored(tmp_path):
    path = tmp_path / "data.txt"
    path.write_text("1.0 2.0 3.0 4.0\n")
    cols = parse_xy_columns(path, 2)
    assert len(cols) == 2
    np.testing.assert_allclose(cols[0], [1.0])
    np.testing.assert_allclose(cols[1], [2.0])


def test_parse_data_file(tmp_path):
    path = tmp_path / "Foo_data.txt"
    path.write_text("1.0 10.0 0.1\n2.0 20.0 0.2\n")
    q, intensity, error = parse_data_file(path)
    np.testing.assert_allclose(q, [1.0, 2.0])
    np.testing.assert_allclose(intensity, [10.0, 20.0])
    np.testing.assert_allclose(error, [0.1, 0.2])


def test_parse_fit_file(tmp_path):
    path = tmp_path / "Foo_fit_01.txt"
    path.write_text("1.0 10.0\n")
    q, intensity = parse_fit_file(path)
    np.testing.assert_allclose(q, [1.0])
    np.testing.assert_allclose(intensity, [10.0])


def test_parse_chi_file(tmp_path):
    path = tmp_path / "Foo_chi_01.txt"
    path.write_text("100 5.5\n")
    moves, chi2 = parse_chi_file(path)
    np.testing.assert_allclose(moves, [100.0])
    np.testing.assert_allclose(chi2, [5.5])


def test_parse_scf_file(tmp_path):
    path = tmp_path / "Foo_scf.txt"
    path.write_text("1.0 0.5 0.01\n")
    r, scf, sigma = parse_scf_file(path)
    np.testing.assert_allclose(r, [1.0])
    np.testing.assert_allclose(scf, [0.5])
    np.testing.assert_allclose(sigma, [0.01])
