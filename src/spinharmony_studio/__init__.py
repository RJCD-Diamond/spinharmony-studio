"""Top level API.

.. data:: __version__
    :type: str

    Version number as calculated by https://github.com/pypa/setuptools_scm
"""

import os

from ._version import __version__

__all__ = ["__version__"]

BASE_PATH = os.path.dirname(os.path.abspath(__file__))
