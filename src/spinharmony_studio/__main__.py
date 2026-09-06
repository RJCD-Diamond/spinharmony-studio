"""Interface for ``python -m spinharmony_studio``."""

import sys

import click

from . import __version__

__all__ = ["main"]


@click.group()
@click.version_option(__version__, "-v", "--version", message="%(version)s")
def main() -> None:
    """Spinharmony Studio command line interface."""


@main.command()
def spinvert() -> None:
    """Launch the spinvert GUI."""
    from spinharmony_studio.spinvert.gui.main_window import run_spinharmony

    run_spinharmony(sys.argv[:1])


@main.command()
def scatty() -> None:
    """Launch the scatty configuration GUI."""
    from spinharmony_studio.scatty.gui.app import main as run_scatty

    run_scatty(sys.argv[:1])


if __name__ == "__main__":
    main()
