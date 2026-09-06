"""Helpers for locating and sanity-checking the external program executables
(spinvert, spincorrel, scatty). Shared by every program window."""

import os
import platform
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from PyQt6.QtWidgets import QMessageBox, QWidget


def resolve_executable(text: str) -> str | None:
    """Locate ``text`` as a file path (with ~ expansion) or a bare name on
    PATH. Returns the resolved path, or None if nothing is there."""
    candidate = Path(text).expanduser()
    if candidate.is_file():
        return str(candidate)
    return shutil.which(text)


# Mach-O magic bytes -> byte order of the file's own header fields. Covers
# both single-arch Mach-O and universal/fat binaries.
_MACHO_MAGICS: dict[bytes, Literal["little", "big"]] = {
    b"\xfe\xed\xfa\xce": "big",  # MH_MAGIC (32-bit)
    b"\xce\xfa\xed\xfe": "little",  # MH_CIGAM (32-bit)
    b"\xfe\xed\xfa\xcf": "big",  # MH_MAGIC_64
    b"\xcf\xfa\xed\xfe": "little",  # MH_MAGIC_64 (Intel/Apple Silicon Macs)
}
_MACHO_FAT_MAGICS = {b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"}
_MACHO_CPU_TYPES = {
    0x00000007: "x86 (32-bit)",
    0x01000007: "x86-64",
    0x0000000C: "ARM (32-bit)",
    0x0100000C: "AArch64",
}


def _macho_arch(head: bytes) -> str | None:
    """
    If ``head`` starts with a Mach-O magic number, return the CPU
    architecture it's built for (or "universal" for a fat binary covering
    multiple), else None.
    """
    if head[:4] in _MACHO_FAT_MAGICS:
        return "universal"
    byteorder = _MACHO_MAGICS.get(head[:4])
    if byteorder is None:
        return None
    cputype = int.from_bytes(head[4:8], byteorder)
    return _MACHO_CPU_TYPES.get(cputype, f"machine 0x{cputype:x}")


def diagnose_executable(path: str) -> str | None:
    """Return a human-readable reason the file at ``path`` cannot be exec'd on
    this machine, or None if it looks runnable."""
    p = Path(path)
    try:
        size = p.stat().st_size
    except OSError as exc:
        return f"Cannot read {path}: {exc}"
    if not p.is_file():
        return f"{path} is not a regular file."
    if not os.access(p, os.X_OK):
        return f"{path} is not marked executable. Run:\n\n    chmod +x {path}"
    if size == 0:
        return f"{path} is empty (0 bytes)."

    try:
        head = p.read_bytes()[:64]
    except OSError as exc:
        return f"Cannot read {path}: {exc}"

    if head[:2] == b"MZ":
        return (
            f"{path} looks like a Windows executable (.exe), which cannot run "
            f"on this machine. Use a binary built for {platform.system()}."
        )
    if head[:4] == b"\x7fELF":
        e_machine = int.from_bytes(head[18:20], "little")
        elf_arch = {
            0x03: "x86 (32-bit)",
            0x3E: "x86-64",
            0x28: "ARM (32-bit)",
            0xB7: "AArch64",
        }.get(e_machine, f"machine 0x{e_machine:02x}")
        host = platform.machine()
        expected = {
            "x86_64": "x86-64",
            "amd64": "x86-64",
            "aarch64": "AArch64",
            "arm64": "AArch64",
            "i686": "x86 (32-bit)",
            "i386": "x86 (32-bit)",
        }.get(host.lower())
        if expected and expected != elf_arch:
            return (
                f"{path} is an ELF binary for {elf_arch}, but this machine is "
                f"{host}. You need a binary built for {host}."
            )
        return None
    macho_arch = _macho_arch(head)
    if macho_arch is not None:
        host = platform.machine()
        expected = {
            "x86_64": "x86-64",
            "amd64": "x86-64",
            "aarch64": "AArch64",
            "arm64": "AArch64",
        }.get(host.lower())
        if expected and macho_arch not in (expected, "universal"):
            return (
                f"{path} is a macOS binary for {macho_arch}, but this machine is "
                f"{host}. You need a binary built for {host}."
            )
        return None
    if head[:2] == b"#!":
        interp = head.split(b"\n", 1)[0][2:].strip().split()
        name = interp[0].decode(errors="replace") if interp else ""
        if name and not Path(name).exists() and not shutil.which(name):
            return (
                f"{path} is a script whose interpreter {name!r} (from its "
                "'#!' line) was not found."
            )
        return None

    if all(b in (9, 10, 13) or 32 <= b <= 126 for b in head):
        return (
            f"{path} looks like a text file, not a program. Point the executable "
            "setting at the compiled binary."
        )
    return (
        f"{path} is not a recognised executable format (no ELF or '#!' header). "
        "It may be corrupt or built for another OS."
    )


def prepare_executable(
    parent: QWidget | None,
    path: str,
    label: str,
    log: Callable[[str], None],
) -> str | None:
    """Resolve and sanity-check an executable path for ``label`` (e.g.
    "spinvert"), showing a warning dialog and returning None on any problem."""
    path = path.strip()
    if not path:
        QMessageBox.warning(
            parent,
            f"No {label} executable",
            f"Choose it via  File → “Set {label} executable…”  first.",
        )
        return None
    resolved = resolve_executable(path)
    if resolved is None:
        QMessageBox.warning(
            parent,
            "Executable not found",
            f"No file found at {path!r} and nothing by that name on PATH.\n\n"
            f"Point the {label} executable at the compiled binary.",
        )
        return None
    problem = diagnose_executable(resolved)
    if problem is not None:
        log(problem + "\n")
        QMessageBox.warning(parent, f"Cannot run {label}", problem)
        return None
    return resolved
