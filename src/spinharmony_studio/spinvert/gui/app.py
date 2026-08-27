"""Entry point for the Spinvert GUI."""

import sys
from collections.abc import Sequence

from PyQt6.QtWidgets import QApplication

from spinharmony_studio.spinvert.gui.main_window import MainWindow

__all__ = ["main"]


def main(args: Sequence[str] | None = None) -> None:
    app = QApplication(list(args) if args is not None else sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
