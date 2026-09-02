"""Small persisted store for GUI preferences.

This remembers the paths to the external programs (spinvert, spincorrel, scatty)
so the user picks them once, plus the last working directory / title so the last
config reloads on the next launch. The file is JSON, in the platform's per-user
application-config directory (via ``QStandardPaths``).
"""

import json
from pathlib import Path

from PyQt6.QtCore import QStandardPaths

_EXECUTABLE_KEY = "spinvert_executable"
_SPINCORREL_KEY = "spincorrel_executable"
_SCATTY_KEY = "scatty_executable"
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


def settings_file() -> Path:
    """Absolute path of the settings JSON file (it may not exist yet)."""
    location = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppConfigLocation
    )
    if location:
        base = Path(location)
    else:
        base = Path.home() / ".config" / "spinharmony-studio"
    return base / "settings.json"


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


def load_executable_path() -> str | None:
    """The saved spinvert executable path, or None if unset / file missing."""
    return load_path(_EXECUTABLE_KEY)


def save_executable_path(path: str) -> Path:
    """Persist the spinvert executable path. Returns the settings file path."""
    return save_path(_EXECUTABLE_KEY, path)


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


if __name__ == "__main__":
    print(settings_file())
