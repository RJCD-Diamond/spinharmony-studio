"""Small persisted store for GUI preferences.

Currently this only remembers the path to the spinvert executable so the user
picks it once and it is restored on the next launch. The file is JSON, in the
platform's per-user application-config directory (via ``QStandardPaths``).
"""

import json
from pathlib import Path

from PyQt6.QtCore import QStandardPaths

_EXECUTABLE_KEY = "spinvert_executable"


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
    value = _read().get(_EXECUTABLE_KEY)
    if isinstance(value, str) and value.strip():
        return value
    return None


def save_executable_path(path: str) -> Path:
    """Persist the spinvert executable path. Returns the settings file path."""
    data = _read()
    data[_EXECUTABLE_KEY] = path
    _write(data)
    return settings_file()


if __name__ == "__main__":
    print(settings_file())
