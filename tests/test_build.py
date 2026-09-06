"""Tests for :mod:`spinharmony_studio.build`."""

import base64
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from spinharmony_studio import build


def _make_zip(zip_path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)


def test_gfortran_available_true_when_found():
    with patch.object(build.shutil, "which", return_value="/usr/bin/gfortran"):
        assert build.gfortran_available() is True


def test_gfortran_available_false_when_missing():
    with patch.object(build.shutil, "which", return_value=None):
        assert build.gfortran_available() is False


def test_compile_fortran_raises_when_gfortran_missing(tmp_path):
    with patch.object(build, "gfortran_available", return_value=False):
        with pytest.raises(FileNotFoundError):
            build.compile_fortran(tmp_path / "foo.f90")


def test_builds_expected_command(tmp_path):
    source = tmp_path / "foo.f90"
    with (
        patch.object(build, "gfortran_available", return_value=True),
        patch.object(build.subprocess, "run") as mock_run,
    ):
        build.compile_fortran(source)
    cmd = mock_run.call_args.args[0]
    assert cmd[0] == "gfortran"
    assert cmd[1] == str(source)
    assert cmd[2] == "-o"
    assert cmd[3] == str(tmp_path / "foo")
    assert cmd[4] == "-O3"


def test_explicit_output_and_optimization(tmp_path):
    source = tmp_path / "foo.f90"
    out = tmp_path / "bar"
    with (
        patch.object(build, "gfortran_available", return_value=True),
        patch.object(build.subprocess, "run") as mock_run,
    ):
        build.compile_fortran(source, output_filepath=out, optimization="O2")
    cmd = mock_run.call_args.args[0]
    assert cmd[2:5] == ["-o", str(out), "-O2"]


def test_extra_flags_appended(tmp_path):
    source = tmp_path / "foo.f90"
    with (
        patch.object(build, "gfortran_available", return_value=True),
        patch.object(build.subprocess, "run") as mock_run,
    ):
        build.compile_fortran(source, extra_flags=["-fopenmp"])
    cmd = mock_run.call_args.args[0]
    assert cmd[-1] == "-fopenmp"


def test_unzip_file_extracts_to_sibling_by_default(tmp_path):
    zip_path = tmp_path / "archive.zip"
    _make_zip(zip_path, {"a/b.txt": b"hello"})
    result = build.unzip_file(zip_path)
    assert result == tmp_path
    assert (tmp_path / "a" / "b.txt").read_text() == "hello"


def test_unzip_file_extracts_to_given_directory(tmp_path):
    zip_path = tmp_path / "archive.zip"
    _make_zip(zip_path, {"file.txt": b"data"})
    target = tmp_path / "out"
    result = build.unzip_file(zip_path, extract_to=target)
    assert result == target
    assert (target / "file.txt").read_text() == "data"


def test_run_make_raises_when_gfortran_missing(tmp_path):
    with patch.object(build, "gfortran_available", return_value=False):
        with pytest.raises(FileNotFoundError):
            build.run_make(tmp_path)


def test_raises_when_no_makefile(tmp_path):
    with patch.object(build, "gfortran_available", return_value=True):
        with pytest.raises(FileNotFoundError, match="No Makefile"):
            build.run_make(tmp_path)


def test_raises_with_output_on_nonzero_exit(tmp_path):
    (tmp_path / "Makefile").write_text("")
    fake_result = MagicMock(returncode=1, stdout="out", stderr="err")
    with (
        patch.object(build, "gfortran_available", return_value=True),
        patch.object(build.subprocess, "run", return_value=fake_result),
    ):
        with pytest.raises(RuntimeError, match="make.*failed"):
            build.run_make(tmp_path)


def test_returns_result_on_success(tmp_path):
    (tmp_path / "Makefile").write_text("")
    fake_result = MagicMock(returncode=0)
    with (
        patch.object(build, "gfortran_available", return_value=True),
        patch.object(build.subprocess, "run", return_value=fake_result) as mock_run,
    ):
        result = build.run_make(tmp_path)
    assert result is fake_result
    assert mock_run.call_args.kwargs["cwd"] == str(tmp_path)


def test_download_icloud_file_invalid_url_raises():
    with pytest.raises(ValueError, match="share token"):
        build.download_icloud_file("https://example.com/not-icloud")


def test_successful_download(tmp_path):
    basename_b64 = base64.b64encode(b"myfile").decode()
    resolve_payload = {
        "results": [
            {
                "rootRecord": {
                    "fields": {
                        "fileContent": {
                            "value": {
                                "downloadURL": "https://example.com/dl?f=${f}",
                                "size": 5,
                            }
                        },
                        "encryptedBasename": {"value": basename_b64},
                        "extension": {"value": "zip"},
                    }
                }
            }
        ]
    }
    mock_resolve_resp = MagicMock()
    mock_resolve_resp.json.return_value = resolve_payload
    mock_resolve_resp.raise_for_status.return_value = None

    mock_download_resp = MagicMock()
    mock_download_resp.raise_for_status.return_value = None
    mock_download_resp.iter_content.return_value = [b"hello"]
    mock_download_resp.__enter__.return_value = mock_download_resp
    mock_download_resp.__exit__.return_value = False

    mock_session = MagicMock()
    mock_session.post.return_value = mock_resolve_resp
    mock_session.get.return_value = mock_download_resp

    with patch.object(build.requests, "Session", return_value=mock_session):
        result = build.download_icloud_file(
            "https://www.icloud.com/iclouddrive/TOKEN123#myfile", tmp_path
        )

    assert result == tmp_path / "myfile.zip"
    assert result.read_bytes() == b"hello"
    get_url = mock_session.get.call_args.args[0]
    assert "myfile.zip" in get_url


def test_size_mismatch_raises(tmp_path):
    basename_b64 = base64.b64encode(b"myfile").decode()
    resolve_payload = {
        "results": [
            {
                "rootRecord": {
                    "fields": {
                        "fileContent": {
                            "value": {
                                "downloadURL": "https://example.com/dl?f=${f}",
                                "size": 999,
                            }
                        },
                        "encryptedBasename": {"value": basename_b64},
                    }
                }
            }
        ]
    }
    mock_resolve_resp = MagicMock()
    mock_resolve_resp.json.return_value = resolve_payload
    mock_resolve_resp.raise_for_status.return_value = None

    mock_download_resp = MagicMock()
    mock_download_resp.raise_for_status.return_value = None
    mock_download_resp.iter_content.return_value = [b"hi"]
    mock_download_resp.__enter__.return_value = mock_download_resp
    mock_download_resp.__exit__.return_value = False

    mock_session = MagicMock()
    mock_session.post.return_value = mock_resolve_resp
    mock_session.get.return_value = mock_download_resp

    with patch.object(build.requests, "Session", return_value=mock_session):
        with pytest.raises(RuntimeError, match="Downloaded"):
            build.download_icloud_file(
                "https://www.icloud.com/iclouddrive/TOKEN#f", tmp_path
            )


def test_malformed_payload_raises(tmp_path):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"results": []}
    mock_resp.raise_for_status.return_value = None
    mock_session = MagicMock()
    mock_session.post.return_value = mock_resp

    with patch.object(build.requests, "Session", return_value=mock_session):
        with pytest.raises(RuntimeError, match="did not resolve"):
            build.download_icloud_file(
                "https://www.icloud.com/iclouddrive/TOKEN#f", tmp_path
            )


def test_unpack_extracts_into_stem_named_directory(tmp_path):
    zip_path = tmp_path / "spinvert_18Mar19exe.zip"
    _make_zip(zip_path, {"spinvert_18Mar19/programs/Makefile": b""})
    extract_to = build.unpack(zip_path)
    assert extract_to == tmp_path / "spinvert_18Mar19exe"
    assert (extract_to / "spinvert_18Mar19" / "programs" / "Makefile").is_file()


def test_removes_stale_directory_first(tmp_path):
    zip_path = tmp_path / "archive.zip"
    _make_zip(zip_path, {"new.txt": b""})
    stale_dir = tmp_path / "archive"
    stale_dir.mkdir()
    (stale_dir / "old.txt").write_text("stale")
    build.unpack(zip_path)
    assert not (stale_dir / "old.txt").exists()
    assert (stale_dir / "new.txt").exists()


def test_find_make_dir_finds_single_match(tmp_path):
    (tmp_path / "spinvert_18Mar19" / "programs").mkdir(parents=True)
    result = build.find_make_dir(tmp_path, "programs")
    assert result == tmp_path / "spinvert_18Mar19" / "programs"


def test_ignores_macosx_sidecar(tmp_path):
    (tmp_path / "spinvert_18Mar19" / "programs").mkdir(parents=True)
    (tmp_path / "__MACOSX" / "spinvert_18Mar19" / "programs").mkdir(parents=True)
    result = build.find_make_dir(tmp_path, "programs")
    assert "__MACOSX" not in result.parts


def test_no_match_raises(tmp_path):
    with pytest.raises(RuntimeError, match="found 0"):
        build.find_make_dir(tmp_path, "programs")


def test_multiple_matches_raises(tmp_path):
    (tmp_path / "a" / "programs").mkdir(parents=True)
    (tmp_path / "b" / "programs").mkdir(parents=True)
    with pytest.raises(RuntimeError, match="found 2"):
        build.find_make_dir(tmp_path, "programs")


def test_nested_parts(tmp_path):
    (tmp_path / "spinteract_140923" / "source" / "minuit").mkdir(parents=True)
    result = build.find_make_dir(tmp_path, "source", "minuit")
    assert result.name == "minuit"


def test_clean_build_dir_removes_build_artifacts(tmp_path):
    (tmp_path / "foo.o").write_text("")
    (tmp_path / "bar.mod").write_text("")
    (tmp_path / "lib.a").write_text("")
    (tmp_path / "keep.f90").write_text("")
    build.clean_build_dir(tmp_path)
    remaining = {p.name for p in tmp_path.iterdir()}
    assert remaining == {"keep.f90"}


def test_download_spinharmony_downloads_all_three_and_creates_dir(tmp_path):
    target = tmp_path / "nested"
    with patch.object(
        build, "download_icloud_file", side_effect=lambda url, loc: loc / "x.zip"
    ) as mock_dl:
        result = build.download_spinharmony(target)
    assert target.is_dir()
    assert result == (target / "x.zip", target / "x.zip", target / "x.zip")
    assert mock_dl.call_count == 3


def test_download_spinharmony_defaults_to_app_data_dir(tmp_path):
    with (
        patch.object(build, "app_data_dir", lambda: tmp_path),
        patch.object(
            build, "download_icloud_file", side_effect=lambda url, loc: loc / "x.zip"
        ),
    ):
        build.download_spinharmony()
    assert tmp_path.is_dir()


def test_find_instructions_pdf_finds_top_level_pdf(tmp_path):
    (tmp_path / "prog_instructions.pdf").write_bytes(b"x" * 100)
    result = build.find_instructions_pdf(tmp_path)
    assert result is not None
    assert result.name == "prog_instructions.pdf"


def test_find_instructions_pdf_excludes_macosx_sidecar(tmp_path):
    (tmp_path / "__MACOSX").mkdir()
    (tmp_path / "__MACOSX" / "._prog_instructions.pdf").write_bytes(b"x")
    assert build.find_instructions_pdf(tmp_path) is None


def test_excludes_appledouble_stub_outside_macosx(tmp_path):
    (tmp_path / "._hidden.pdf").write_bytes(b"x")
    assert build.find_instructions_pdf(tmp_path) is None


def test_prefers_instructions_named_file_over_nested_other_pdf(tmp_path):
    (tmp_path / "top_instructions.pdf").write_bytes(b"x" * 10)
    nested = tmp_path / "source" / "minuit" / "doc"
    nested.mkdir(parents=True)
    (nested / "minuit.pdf").write_bytes(b"x" * 10)
    result = build.find_instructions_pdf(tmp_path)
    assert result is not None
    assert result.name == "top_instructions.pdf"


def test_find_instructions_pdf_no_pdf_returns_none(tmp_path):
    assert build.find_instructions_pdf(tmp_path) is None


def test_find_program_instructions_pdf_finds_matching_program_folder(tmp_path):
    folder = tmp_path / "spinvert_18Mar19exe" / "spinvert_18Mar19"
    folder.mkdir(parents=True)
    (folder / "spinvert_instructions.pdf").write_bytes(b"x" * 10)
    result = build.find_program_instructions_pdf("spinvert", tmp_path)
    assert result is not None
    assert result.name == "spinvert_instructions.pdf"


def test_does_not_cross_contaminate_between_programs(tmp_path):
    for prog in ("spinvert_18Mar19exe", "scatty_14Oct22exe"):
        folder = tmp_path / prog
        folder.mkdir(parents=True)
        (folder / f"{prog}_instructions.pdf").write_bytes(b"x" * 10)
    result = build.find_program_instructions_pdf("scatty", tmp_path)
    assert result is not None
    assert "scatty" in result.name


def test_missing_app_location_returns_none(tmp_path):
    assert build.find_program_instructions_pdf("spinvert", tmp_path / "nope") is None


def test_no_matching_folder_returns_none(tmp_path):
    (tmp_path / "unrelated").mkdir()
    assert build.find_program_instructions_pdf("spinvert", tmp_path) is None


def test_find_program_instructions_pdf_defaults_to_app_data_dir(tmp_path):
    with patch.object(build, "app_data_dir", lambda: tmp_path):
        assert build.find_program_instructions_pdf("spinvert") is None


def test_passes_for_existing_path(tmp_path):
    f = tmp_path / "exists.txt"
    f.write_text("")
    assert build._require(f) == f


def test_raises_for_missing_path(tmp_path):
    with pytest.raises(RuntimeError, match="did not produce"):
        build._require(tmp_path / "missing.txt")


def test_build_spinvert(tmp_path):
    extract_to = tmp_path / "extracted"
    programs = extract_to / "spinvert_18Mar19" / "programs"
    programs.mkdir(parents=True)
    (programs / "spinvert").write_text("")
    (programs / "spincorrel").write_text("")

    with (
        patch.object(build, "unpack", return_value=extract_to),
        patch.object(build, "run_make") as mock_make,
    ):
        result = build.build_spinvert("dummy.zip")
    assert mock_make.called
    assert result == {
        "spinvert": programs / "spinvert",
        "spincorrel": programs / "spincorrel",
    }


def test_build_scatty(tmp_path):
    extract_to = tmp_path / "extracted"
    programs = extract_to / "scatty_14Oct22" / "programs"
    programs.mkdir(parents=True)
    (programs / "scatty").write_text("")

    with (
        patch.object(build, "unpack", return_value=extract_to),
        patch.object(build, "run_make"),
    ):
        result = build.build_scatty("dummy.zip")
    assert result == {"scatty": programs / "scatty"}


def test_build_spinteract(tmp_path):
    extract_to = tmp_path / "extracted"
    minuit = extract_to / "spinteract_140923" / "source" / "minuit"
    spinteract_dir = extract_to / "spinteract_140923" / "source" / "spinteract"
    minuit.mkdir(parents=True)
    spinteract_dir.mkdir(parents=True)
    (minuit / "libminuit.a").write_text("")
    (spinteract_dir / "spinteract").write_text("")

    with (
        patch.object(build, "unpack", return_value=extract_to),
        patch.object(build, "clean_build_dir"),
        patch.object(build, "run_make"),
    ):
        result = build.build_spinteract("dummy.zip")
    assert result == {"spinteract": spinteract_dir / "spinteract"}
    assert (spinteract_dir / "libminuit.a").is_file()


def test_build_spinplot_and_spindist_copies_and_compiles(tmp_path):
    def fake_compile(source, *args, **kwargs):
        output = str(source).rsplit(".", 1)[0]
        Path(output).write_text("")

    with patch.object(build, "compile_fortran", side_effect=fake_compile):
        result = build.build_spinplot_and_spindist(tmp_path)

    assert result["spindist"] == tmp_path / "spindist"
    assert result["spinplot"] == tmp_path / "spinplot"
    assert result["spindist"].is_file()
    assert result["spinplot"].is_file()
    assert (tmp_path / "spindist.f90").is_file()
    assert (tmp_path / "spinplot.f").is_file()


def test_save_executable_paths_saves_each_via_its_settings_function(tmp_path):
    from spinharmony_studio import settings

    with patch.object(settings, "app_data_dir", lambda: tmp_path):
        build.save_executable_paths(
            {"spinvert": tmp_path / "spinvert", "scatty": tmp_path / "scatty"}
        )
        assert settings.load_spinvert_path() == str(tmp_path / "spinvert")
        assert settings.load_scatty_path() == str(tmp_path / "scatty")


def test_unzip_and_build_spinharmony_merges_all_three_results():
    with (
        patch.object(build, "build_spinvert", return_value={"spinvert": "a"}),
        patch.object(build, "build_scatty", return_value={"scatty": "b"}),
        patch.object(build, "build_spinteract", return_value={"spinteract": "c"}),
    ):
        result = build.unzip_and_build_spinharmony("v.zip", "s.zip", "i.zip")
    assert result == {"spinvert": "a", "scatty": "b", "spinteract": "c"}


def test_setup_spinharmony_raises_without_gfortran():
    with patch.object(build, "gfortran_available", return_value=False):
        with pytest.raises(FileNotFoundError, match="gfortran"):
            build.setup_spinharmony()


def test_happy_path_orchestrates_and_saves(tmp_path):
    with (
        patch.object(build, "gfortran_available", return_value=True),
        patch.object(
            build,
            "download_spinharmony",
            return_value=("v.zip", "s.zip", "i.zip"),
        ),
        patch.object(
            build,
            "unzip_and_build_spinharmony",
            return_value={"spinvert": tmp_path / "spinvert"},
        ) as mock_unzip_build,
        patch.object(
            build,
            "build_spinplot_and_spindist",
            return_value={"spindist": tmp_path / "spindist"},
        ),
        patch.object(build, "save_executable_paths") as mock_save,
    ):
        result = build.setup_spinharmony(tmp_path)

    mock_unzip_build.assert_called_once_with("v.zip", "s.zip", "i.zip")
    assert result == {
        "spinvert": tmp_path / "spinvert",
        "spindist": tmp_path / "spindist",
    }
    mock_save.assert_called_once_with(result)


def test_defaults_app_location(tmp_path):
    with (
        patch.object(build, "app_data_dir", lambda: tmp_path),
        patch.object(build, "gfortran_available", return_value=True),
        patch.object(
            build, "download_spinharmony", return_value=("v", "s", "i")
        ) as mock_download,
        patch.object(build, "unzip_and_build_spinharmony", return_value={}),
        patch.object(build, "build_spinplot_and_spindist", return_value={}),
        patch.object(build, "save_executable_paths"),
    ):
        build.setup_spinharmony()
    mock_download.assert_called_once_with(tmp_path)
