import base64
import re
import shutil
import subprocess
import urllib.parse
import uuid
import zipfile
from pathlib import Path

import requests

from spinharmony_studio.settings import app_data_dir
from spinharmony_studio.source_urls import (
    SCATTY_DOWNLOAD_URL,
    SPINTERACT_DOWNLOAD_URL,
    SPINVERT_DOWNLOAD_URL,
)

# iCloud's public CloudKit web service. The /iclouddrive/<token> URL only serves
# the iCloud web app HTML; the actual file bytes have to be resolved through this.
_ICLOUD_RESOLVE_URL = (
    "https://ckdatabasews.icloud.com/database/1/com.apple.cloudkit/production"
    "/public/records/resolve"
)


def gfortran_available():
    """
    Check whether gfortran is installed and available on the system PATH.

    Returns:
        bool: True if gfortran is found, False otherwise.
    """
    return shutil.which("gfortran") is not None


def compile_fortran(
    source_filepath: str | Path,
    output_filepath: str | Path | None = None,
    optimization: str = "O3",
    extra_flags: str | None = None,
):

    if not gfortran_available():
        raise FileNotFoundError("gfortran or gcc must be installed first!")

    if output_filepath is None:
        output_filepath = str(source_filepath).rsplit(".", 1)[0]
    # fmt: off
    cmd = ["gfortran", str(source_filepath), "-o", str(output_filepath), f"-{optimization}"] # noqa: E501
    # fmt: on

    if extra_flags:
        cmd.extend(extra_flags)

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result


def unzip_file(zip_path: str | Path, extract_to: str | Path | None = None) -> Path:
    """
    Unzip a file to a specified directory.

    Args:
        zip_path: Path to the zip file.
        extract_to: Directory to extract the contents to. If None, extracts to
            the same directory as the zip file.

    Returns:
        Path: The directory the contents were extracted to.
    """
    zip_path = Path(zip_path)
    extract_to = Path(extract_to) if extract_to is not None else zip_path.parent

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(extract_to)

    return extract_to


def run_make(source_folder: str | Path) -> subprocess.CompletedProcess:
    """
    Run ``make`` in ``source_folder``.

    Unlike a bare ``subprocess.run(..., check=True)``, a failure here raises with
    make's own stdout/stderr attached, so you can see *why* the build broke
    instead of just ``exit status 2``.
    """
    if not gfortran_available():
        raise FileNotFoundError("gfortran must be installed first!")

    source_folder = Path(source_folder)
    if not (source_folder / "Makefile").is_file():
        raise FileNotFoundError(f"No Makefile in {source_folder}")

    result = subprocess.run(
        ["make"],
        cwd=str(source_folder),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"`make` failed in {source_folder} (exit {result.returncode})\n"
            f"----- stdout -----\n{result.stdout}\n"
            f"----- stderr -----\n{result.stderr}"
        )
    return result


def download_icloud_file(share_url: str, output_path: str | Path | None = None) -> Path:
    """
    Download a single file shared from iCloud Drive via a public share link.

    A link such as ``https://www.icloud.com/iclouddrive/<token>#<name>`` points at
    the iCloud web app, not the file. This resolves the share token to its
    CloudKit record, extracts the signed ``downloadURL``, and fetches the bytes.

    Args:
        share_url: The public ``iclouddrive`` share URL.
        output_path: File path, or a directory to save into using the file's own
            name. If omitted, the file's own name is used in the current dir.

    Returns:
        Path: The path the file was written to.
    """
    match = re.search(r"iclouddrive/([^#?/]+)", share_url)
    if not match:
        raise ValueError("Could not parse share token from URL")
    token = match.group(1)

    session = requests.Session()
    session.headers.update(
        {
            "Origin": "https://www.icloud.com",
            "Referer": "https://www.icloud.com/",
            "Content-Type": "application/json",
        }
    )

    resp = session.post(
        _ICLOUD_RESOLVE_URL,
        params={"clientId": str(uuid.uuid4())},
        json={"shortGUIDs": [{"value": token}]},
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()

    try:
        root = payload["results"][0]["rootRecord"]
        fields = root["fields"]
        file_content = fields["fileContent"]["value"]
        download_url: str = file_content["downloadURL"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(
            f"Share did not resolve to a single downloadable file: {payload}"
        ) from exc

    # Reconstruct the file's real name from the record.
    try:
        basename = base64.b64decode(fields["encryptedBasename"]["value"]).decode()
        extension = fields.get("extension", {}).get("value", "")
        remote_name = f"{basename}.{extension}" if extension else basename
    except Exception:
        remote_name = "downloaded_file"

    if output_path is None:
        output_path = Path(remote_name)
    else:
        output_path = Path(output_path)
        if output_path.is_dir():
            output_path = output_path / remote_name

    # Apple leaves a ${f} placeholder in the signed URL for the filename.
    download_url = download_url.replace("${f}", urllib.parse.quote(output_path.name))

    written = 0
    with session.get(download_url, stream=True, timeout=120) as file_resp:
        file_resp.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in file_resp.iter_content(chunk_size=1 << 16):
                f.write(chunk)
                written += len(chunk)
                print(f"Downloading {output_path.name}: {written} bytes", end="\r")
    print()

    expected = file_content.get("size")
    if expected is not None and written != expected:
        raise RuntimeError(f"Downloaded {written} bytes but record reports {expected}")

    print(f"Saved to {output_path} ({written} bytes)")
    return output_path


# ---------------------------------------------------------------------------
# Building the three SpinHarmony components
# ---------------------------------------------------------------------------


def unpack(zip_path: str | Path) -> Path:
    """
    Extract ``zip_path`` into a fresh sibling directory named after the zip.

    Each component gets its own directory so the ``*/programs`` lookups below
    can't collide when several archives are unpacked next to each other.
    """
    zip_path = Path(zip_path)
    extract_to = zip_path.with_suffix("")
    if extract_to.exists():
        shutil.rmtree(extract_to)
    unzip_file(zip_path, extract_to=extract_to)
    return extract_to


def find_make_dir(root: str | Path, *parts: str) -> Path:
    """
    Find the single directory ``root/*/parts...`` that holds a Makefile.

    The archives nest their Makefiles a few levels down and the top-level
    folder name carries a version date (``spinvert_18Mar19`` etc.), so the path
    is discovered rather than hard-coded. The ``__MACOSX`` sidecar tree that
    macOS zips include is ignored.
    """
    root = Path(root)
    matches = [
        p
        for p in root.glob("/".join(("*", *parts)))
        if p.is_dir() and "__MACOSX" not in p.parts
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected exactly one {'/'.join(parts)} directory under {root}, "
            f"found {len(matches)}: {matches}"
        )
    return matches[0]


def clean_build_dir(make_dir: str | Path) -> None:
    """
    Delete stale build products from ``make_dir``.

    The archives ship object files and libraries prebuilt for macOS/Windows;
    left in place they can mask a compile or link error on this machine.
    """
    make_dir = Path(make_dir)
    for pattern in ("*.o", "*.mod", "*.MOD", "*.a", "*.so"):
        for path in make_dir.glob(pattern):
            path.unlink()


def download_spinharmony(
    app_location: str | Path | None = None,
) -> tuple[Path, Path, Path]:
    """
    Download the spinvert, scatty and spinteract source zips from iCloud.

    Args:
        app_location: Directory to download into. Defaults to ``app_data_dir()``.

    Returns:
        The (spinvert, scatty, spinteract) zip paths.
    """
    if app_location is None:
        app_location = app_data_dir()
    app_location = Path(app_location)
    app_location.mkdir(parents=True, exist_ok=True)

    print(f"Downloading SpinHarmony sources to {app_location}...")
    spinvert_zip = download_icloud_file(SPINVERT_DOWNLOAD_URL, app_location)
    scatty_zip = download_icloud_file(SCATTY_DOWNLOAD_URL, app_location)
    spinteract_zip = download_icloud_file(SPINTERACT_DOWNLOAD_URL, app_location)
    return spinvert_zip, scatty_zip, spinteract_zip


def build_spinvert(zip_path: str | Path) -> dict[str, Path]:
    """Unzip and build spinvert; returns {"spinvert": ..., "spincorrel": ...}."""
    extract_to = unpack(zip_path)

    programs = find_make_dir(extract_to, "programs")
    clean_build_dir(programs)
    print(f"Building spinvert in {programs}...")
    run_make(programs)

    return {name: _require(programs / name) for name in ("spinvert", "spincorrel")}


def build_scatty(zip_path: str | Path) -> dict[str, Path]:
    """Unzip and build scatty; returns {"scatty": ...}."""
    extract_to = unpack(zip_path)

    programs = find_make_dir(extract_to, "programs")
    clean_build_dir(programs)
    print(f"Building scatty in {programs}...")
    run_make(programs)

    return {"scatty": _require(programs / "scatty")}


def build_spinteract(zip_path: str | Path) -> dict[str, Path]:
    """
    Unzip and build spinteract; returns {"spinteract": ...}.

    spinteract links against ``libminuit.a``, so the bundled minuit library is
    built first and copied into the spinteract source directory.
    """
    extract_to = unpack(zip_path)

    minuit = find_make_dir(extract_to, "source", "minuit")
    clean_build_dir(minuit)
    print(f"Building minuit in {minuit}...")
    run_make(minuit)
    libminuit = _require(minuit / "libminuit.a")

    spinteract = find_make_dir(extract_to, "source", "spinteract")
    clean_build_dir(spinteract)
    shutil.copy2(libminuit, spinteract / "libminuit.a")
    print(f"Building spinteract in {spinteract}...")
    run_make(spinteract)

    return {"spinteract": _require(spinteract / "spinteract")}


def _require(path: Path) -> Path:
    if not path.exists():
        raise RuntimeError(f"make did not produce {path}")
    return path


def unzip_and_build_spinharmony(
    spinvert_zip_path: str | Path,
    scatty_zip_path: str | Path,
    spinteract_zip_path: str | Path,
) -> dict[str, Path]:
    """
    Unzip and build all three components from their downloaded zips.

    Returns:
        Mapping of executable name (spinvert, spincorrel, scatty, spinteract)
        to the built binary's path.
    """
    executables: dict[str, Path] = {}
    executables.update(build_spinvert(spinvert_zip_path))
    executables.update(build_scatty(scatty_zip_path))
    executables.update(build_spinteract(spinteract_zip_path))
    return executables


def setup_spinharmony(app_location: str | Path | None = None) -> dict[str, Path]:
    """
    Download, unzip and build all three SpinHarmony components.

    Returns:
        Mapping of executable name (spinvert, spincorrel, scatty, spinteract)
        to the built binary's path.
    """
    if not gfortran_available():
        raise FileNotFoundError("gfortran must be installed to build SpinHarmony")

    spinvert_zip, scatty_zip, spinteract_zip = download_spinharmony(app_location)
    executables = unzip_and_build_spinharmony(spinvert_zip, scatty_zip, spinteract_zip)

    print("\nAll components built:")
    for name, path in executables.items():
        print(f"  {name}: {path}")
    return executables


if __name__ == "__main__":
    executables = setup_spinharmony()
