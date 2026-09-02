import subprocess
from pathlib import Path


def compile_fortran(
    source_filepath: str | Path,
    output_filepath: str | Path | None,
    optimization: str = "O3",
    extra_flags: str | None = None,
):
    if output_filepath is None:
        output_filepath = str(source_filepath).rsplit(".", 1)[0]
    # fmt: off
    cmd = ["gfortran", str(source_filepath), "-o", str(output_filepath), f"-{optimization}"] # noqa: E501
    # fmt: on

    if extra_flags:
        cmd.extend(extra_flags)

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result
