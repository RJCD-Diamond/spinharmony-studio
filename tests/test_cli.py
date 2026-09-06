import subprocess
import sys
from unittest.mock import patch

from click.testing import CliRunner

from spinharmony_studio import __version__
from spinharmony_studio.__main__ import main


def test_cli_version():
    cmd = [sys.executable, "-m", "spinharmony_studio", "--version"]
    assert subprocess.check_output(cmd).decode().strip() == __version__


def test_no_subcommand_shows_usage():
    result = CliRunner().invoke(main, [])
    assert result.exit_code != 0
    assert "Usage" in result.output


def test_spinvert_subcommand_launches_gui():
    with patch(
        "spinharmony_studio.spinvert.gui.main_window.run_spinharmony"
    ) as mock_run:
        result = CliRunner().invoke(main, ["spinvert"])
    assert result.exit_code == 0
    mock_run.assert_called_once()


def test_scatty_subcommand_launches_gui():
    with patch("spinharmony_studio.scatty.gui.app.main") as mock_run:
        result = CliRunner().invoke(main, ["scatty"])
    assert result.exit_code == 0
    mock_run.assert_called_once()
