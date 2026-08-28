"""Shared base for the plain-text ``KEYWORD value ...`` configuration files used
by the external programs (Spinvert, Scatty, ...).

Each concrete config is a pydantic model that subclasses :class:`KeywordConfig`
and implements :meth:`KeywordConfig._config_lines` -- the ordered keyword lines
for its own format. This base contributes:

* ``to_text`` / ``to_file`` -- rendering and writing, with a filename check,
* value-formatting helpers (:meth:`fmt_num`, :meth:`fmt_seq`, :meth:`keyword`),

so every config type produces and writes files the same way, and a new config
class only has to describe *its* keywords.
"""

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict


def format_number(value: float) -> str:
    """Compact fixed/scientific formatting that round-trips cleanly and trims
    needless trailing zeros (``8.5`` not ``8.5000000000``)."""
    return f"{value:.10g}"


class KeywordConfig(BaseModel):
    """Base class for keyword/value text-config models."""

    model_config = ConfigDict(populate_by_name=True, validate_by_name=True)

    #: Exact filename these configs must be written to. ``None`` accepts any
    #: name; a subclass whose filename is variable (e.g. ``[title]_config.txt``)
    #: overrides :meth:`_check_output_name` instead.
    CONFIG_FILENAME: ClassVar[str | None] = None

    # --- subclass hook -----------------------------------------------------

    def _config_lines(self) -> list[str]:
        """Return the ordered keyword lines for this config (no trailing
        newlines). Must be implemented by every concrete subclass."""
        raise NotImplementedError(
            f"{type(self).__name__} must implement _config_lines()"
        )

    # --- export ----------------------------------------------------------

    def to_text(self) -> str:
        """Render this config to its ``KEYWORD value ...`` text form."""
        return "\n".join(self._config_lines()) + "\n"

    def to_file(self, path: str | Path) -> Path:
        """Write :meth:`to_text` to ``path`` after checking the filename.
        Returns the path written."""
        path = Path(path)
        self._check_output_name(path.name)
        path.write_text(self.to_text())
        return path

    @classmethod
    def _check_output_name(cls, name: str) -> None:
        if cls.CONFIG_FILENAME is not None and name != cls.CONFIG_FILENAME:
            raise ValueError(
                f"{cls.__name__} must be written to a file named "
                f"{cls.CONFIG_FILENAME!r}, not {name!r}."
            )

    # --- value-formatting helpers (shared by every subclass) ------------

    @staticmethod
    def fmt_num(value: float) -> str:
        return format_number(value)

    @classmethod
    def fmt_seq(cls, values: Iterable[float]) -> str:
        """Space-joined numbers, e.g. a 3-vector."""
        return " ".join(cls.fmt_num(v) for v in values)

    @classmethod
    def keyword(cls, name: str, *values: object) -> str:
        """Build one ``KEYWORD v1 v2 ...`` line. ``float`` values are formatted
        with :meth:`fmt_num`, sequences are flattened, everything else uses
        ``str()``. With no values it is a bare flag line (just ``KEYWORD``)."""
        parts: list[str] = [name]
        for value in values:
            if isinstance(value, (list, tuple)):
                parts.extend(cls._token(item) for item in value)
            else:
                parts.append(cls._token(value))
        return " ".join(parts)

    @staticmethod
    def _token(value: object) -> str:
        if isinstance(value, bool):
            raise TypeError("bare-flag keywords take no values")
        if isinstance(value, float):
            return format_number(value)
        return str(value)


def split_config_lines(text: str) -> Iterable[tuple[str, list[str]]]:
    """Iterate ``(KEYWORD, [tokens])`` over a keyword/value file's text.

    Blank lines and ``#`` / ``!`` comment lines are skipped; keywords are
    upper-cased. Shared by the subclasses' own parsers.
    """
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", "!")):
            continue
        token, *values = line.split()
        yield token.upper(), values


def require_n(values: Sequence[str], n: int, keyword: str) -> None:
    if len(values) != n:
        raise ValueError(f"{keyword} expects {n} value(s), got {len(values)}: {values}")
