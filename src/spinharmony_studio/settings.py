"""Small persisted store for GUI preferences.

This remembers the paths to the external programs (spinvert, spincorrel, scatty)
so the user picks them once, plus the last working directory / title so the last
config reloads on the next launch. The file is JSON, in the platform's per-user
application-config directory (via ``QStandardPaths``).
"""

import json
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, QStandardPaths

# QStandardPaths.AppConfigLocation is derived from
# QCoreApplication.organizationName()/applicationName(). Those are static
# properties settable without a QApplication instance - set them here, at
# import time, so app_data_dir() resolves to the same directory regardless
# of whether this is imported by the GUI (which used to set them itself,
# after constructing its QApplication) or by a plain script/test. Leaving it
# to the GUI meant any other entry point saw a different (or unnamed,
# argv[0]-based) config directory and silently missed the real settings file.
QCoreApplication.setOrganizationName("DiamondLightSource")
QCoreApplication.setApplicationName("spinharmony-studio")

_SPINVERT_KEY = "spinvert_executable"
_SPINCORREL_KEY = "spincorrel_executable"
_SPINTERACT_KEY = "spinteract_executable"
_SCATTY_KEY = "scatty_executable"
_SPINPLOT_KEY = "spinplot_executable"
_SPINDIST_KEY = "spindist_executable"

_WORKDIR_KEY = "working_directory"
_TITLE_KEY = "title"


def load_path(key: str) -> str | None:
    value = _read().get(key)
    if isinstance(value, str) and value.strip():
        return value
    return None


def save_path(key: str, path: str) -> Path:
    data = _read()
    data[key] = path
    _write(data)
    return settings_file()


def app_data_dir() -> Path:
    location = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppConfigLocation
    )

    if location:
        base = Path(location)
    else:
        base = Path.home() / ".config" / "spinharmony-studio"
    return base


def settings_file() -> Path:
    """Absolute path of the settings JSON file (it may not exist yet)."""

    return app_data_dir() / "settings.json"


def _read() -> dict:
    try:
        data = json.loads(settings_file().read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(data: dict) -> None:
    path = settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def load_spinvert_path() -> str | None:
    """The saved spinvert executable path, or None if unset / file missing."""
    return load_path(_SPINVERT_KEY)


def save_spinvert_path(path: str) -> Path:
    """Persist the spinvert executable path. Returns the settings file path."""
    return save_path(_SPINVERT_KEY, path)


def load_spincorrel_path() -> str | None:
    """The saved spincorrel executable path, or None if unset / file missing."""
    return load_path(_SPINCORREL_KEY)


def save_spincorrel_path(path: str) -> Path:
    """Persist the spincorrel executable path. Returns the settings file path."""
    return save_path(_SPINCORREL_KEY, path)


def load_scatty_path() -> str | None:
    """The saved scatty executable path, or None if unset / file missing."""
    return load_path(_SCATTY_KEY)


def save_scatty_path(path: str) -> Path:
    """Persist the scatty executable path. Returns the settings file path."""
    return save_path(_SCATTY_KEY, path)


def load_spinteract_path() -> str | None:
    """The saved spinteract executable path, or None if unset / file missing."""
    return load_path(_SPINTERACT_KEY)


def save_spinteract_path(path: str) -> Path:
    """Persist the spinteract executable path. Returns the settings file path."""
    return save_path(_SPINTERACT_KEY, path)


def load_spinplot_path() -> str | None:
    """The saved spinplot executable path, or None if unset / file missing."""
    return load_path(_SPINPLOT_KEY)


def save_spinplot_path(path: str) -> Path:
    """Persist the spinplot executable path. Returns the settings file path."""
    return save_path(_SPINPLOT_KEY, path)


def load_spindist_path() -> str | None:
    """The saved spindist executable path, or None if unset / file missing."""
    return load_path(_SPINDIST_KEY)


def save_spindist_path(path: str) -> Path:
    """Persist the spindist executable path. Returns the settings file path."""
    return save_path(_SPINDIST_KEY, path)


def load_last_session() -> tuple[str | None, str | None]:
    """The last (working directory, title), so the previous config reloads."""
    data = _read()
    workdir = data.get(_WORKDIR_KEY)
    title = data.get(_TITLE_KEY)
    return (
        workdir if isinstance(workdir, str) and workdir.strip() else None,
        title if isinstance(title, str) and title.strip() else None,
    )


def save_last_session(workdir: str, title: str) -> Path:
    """Persist the working directory and title. Returns the settings file path."""
    data = _read()
    data[_WORKDIR_KEY] = workdir
    data[_TITLE_KEY] = title
    _write(data)
    return settings_file()


def example_data_dir() -> Path:
    """Return the path to the example data directory shipped with the package."""
    return Path(__file__).parent / "examples" / "TbODCO3"


if __name__ == "__main__":
    print(settings_file())

    print(load_spinvert_path())
