import subprocess
import sys

from spinharmony_studio import __version__


def test_cli_version():
    cmd = [sys.executable, "-m", "spinharmony_studio", "--version"]
    assert subprocess.check_output(cmd).decode().strip() == __version__
