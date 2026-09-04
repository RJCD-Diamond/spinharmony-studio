"""A script to convert the output of spinvert into a suitable format for
spindist and spinplot and then generates input files
calls spindist and spinplot and generates stereographics projections
"""

import glob
import os
import subprocess
from pathlib import Path

import numpy as np

from spinharmony_studio.settings import load_spindist_path, load_spinplot_path

# Specify location of spindist and spinplot
spindist_location = load_spindist_path()
spinplot_location = load_spinplot_path()


def _run_with_input_file(executable: str, input_path: str) -> None:
    """
    Run ``executable``, feeding it ``input_path`` on stdin (the equivalent of
    the shell's ``executable < input_path``), and print whatever it writes to
    stdout/stderr.
    """
    with open(input_path) as stdin_file:
        result = subprocess.run(
            [executable], stdin=stdin_file, capture_output=True, text=True
        )
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)
    if result.returncode != 0:
        raise RuntimeError(
            f"{executable} failed (exit {result.returncode}) on {input_path}"
        )


def count_header_lines(spins_file: str | Path) -> int:
    """
    Count the header lines at the top of a spinvert ``*_spins_NN.txt`` file.

    The header runs up to (but not including) the first line starting with
    ``SPIN``; everything from there on is spin data. This is the
    ``skip_header`` count ``numpy.genfromtxt`` needs, and it isn't fixed
    across files (e.g. it depends on how many ``SITE`` lines the structure has).
    """
    with open(spins_file) as f:
        for header_size, line in enumerate(f):
            if line.lstrip().startswith("SPIN"):
                return header_size
    raise ValueError(f"No line starting with 'SPIN' found in {spins_file}")


def spinplot_auto(data_location: str | Path, number_of_magnetic_ions: int = 1) -> None:
    """

    Adapted from some old code in 2017

    number_of_magnetic_ions
    How many different unique element magnetic ions are in our unit cell?
    """

    data_location = str(data_location)

    if spindist_location is None or spinplot_location is None:
        raise FileNotFoundError(
            "spindist and/or spinplot executable not found. "
            "Please build SpinHarmony first."
        )

    # Title of file
    data_file_name = [f for f in os.listdir(data_location) if f.endswith("_data.txt")]

    name = data_file_name[0].replace("_data.txt", "")

    # Spindist paramters
    value_of_nphi = 40
    value_of_ntheta = 40
    rotation_matrix = "n"
    suffix = "_spinplot.txt"
    spindist_outputname = name + "_spindist.txt"
    input_spindist_name = "input_spindist.txt"

    letters = "spins"

    # Get a list of files in folder that are a text file
    spins_data_list = [
        f for f in os.listdir(data_location) if f.endswith(".txt") and letters in f
    ]
    spins_data_list.sort()
    # Filter list to give files that a only _spins_xx.txt files that contain spin
    # vectors and box information that are to be converted (where xx is integer), etc

    # modify data locations for later saves into folder

    stacked_data = []
    # stacked_spin_box = []

    for data_name in spins_data_list:
        data = os.path.join(data_location, data_name)
        # imports data
        (
            spin_number,
            box_x_coor,
            box_y_coor,
            box_z_coor,
            x_spin_scalar,
            y_spin_scalar,
            z_spin_scalar,
        ) = np.genfromtxt(
            data,
            skip_header=count_header_lines(data),
            usecols=[1, 2, 3, 4, 5, 6, 7],
            unpack=True,
        )
        # stacks the x,y and z scalar to produce a vector for each ion
        spin_vector = np.stack((x_spin_scalar, y_spin_scalar, z_spin_scalar), axis=1)
        # spin_box = np.stack((box_x_coor, box_y_coor, box_z_coor), axis=1)
        # creates suitable data name and location
        new_data_name = os.path.splitext(data_name)[-2]
        new_data_name = new_data_name.replace(letters, "spindist")
        new_data_name = os.path.join(data_location, new_data_name + ".txt")

        print(new_data_name)

        # stack the spins, and the spin numbers of the separate files into a list
        # for later concatenation into 1 file
        stacked_data.append(spin_vector)

        # create a header for each file and save
        header = (
            str(5138008)
            + "       "
            + str(len(spin_vector))
            + "       "
            + str(number_of_magnetic_ions)
            + "\n"
            + str(int(len(spin_vector) / number_of_magnetic_ions))
        )
        np.savetxt(
            new_data_name, spin_vector, delimiter="  ", header=header, comments=""
        )

    print("Spinvert spin files convert complete")

    os.chdir(data_location)

    spindist = open(input_spindist_name, "w+")

    spindist.write(str(len(spins_data_list)) + "\n")

    for i in range(len(spins_data_list)):
        i = i + 1
        if i < 10:
            spindist.write(name + "_" + str(0) + str(i) + suffix + "\n")
        else:
            spindist.write(name + "_" + str(i) + suffix + "\n")

    spindist.write(str(spindist_outputname) + "\n")

    spindist.write(str(value_of_nphi) + "\n")
    spindist.write(str(value_of_ntheta) + "\n")
    spindist.write(str(rotation_matrix) + "\n")
    spindist.close()

    print("Spindist input complete")
    # opens spindist and inputs the input file
    _run_with_input_file(spindist_location, input_spindist_name)

    print("Spindist complete")

    input_spinplot_origin = "input_spinplot_origin.txt"
    spinplot_origin = open(input_spinplot_origin, "w+")

    spinplot_origin.write(spindist_outputname + "\n")
    spinplot_origin.write(name + "_origin.ppm" + "\n")
    spinplot_origin.write("300 300" + "\n")
    spinplot_origin.write("0 0" + "\n")
    spinplot_origin.write("n" + "\n")
    spinplot_origin.write("1" + "\n")
    spinplot_origin.write("t" + "\n")
    spinplot_origin.close()

    _run_with_input_file(spinplot_location, input_spinplot_origin)

    print("Spinplot origin complete")

    input_spinplot_top = "input_spinplot_top.txt"
    spinplot_top = open(input_spinplot_top, "w+")

    spinplot_top.write(spindist_outputname + "\n")
    spinplot_top.write(name + "_top.ppm" + "\n")
    spinplot_top.write("300 300" + "\n")
    spinplot_top.write("0 -1.57" + "\n")
    spinplot_top.write("n" + "\n")
    spinplot_top.write("1" + "\n")
    spinplot_top.write("f" + "\n")
    spinplot_top.close()

    _run_with_input_file(spinplot_location, input_spinplot_top)

    print("Spinplot top complete")

    input_spinplot_bottom = "input_spinplot_bottom.txt"
    spinplot_bottom = open(input_spinplot_bottom, "w+")

    spinplot_bottom.write(spindist_outputname + "\n")
    spinplot_bottom.write(name + "_bottom.ppm" + "\n")
    spinplot_bottom.write("300 300" + "\n")
    spinplot_bottom.write("0 1.57" + "\n")
    spinplot_bottom.write("n" + "\n")
    spinplot_bottom.write("1" + "\n")
    spinplot_bottom.write("f" + "\n")
    spinplot_bottom.close()

    _run_with_input_file(spinplot_location, input_spinplot_bottom)

    print("Spinplot bottom complete")

    # `convert` (ImageMagick) needs the *origin.ppm glob expanded ourselves,
    # since subprocess (unlike os.system) doesn't run the command through a
    # shell.
    origin_frames = sorted(glob.glob("*origin.ppm"))
    if origin_frames:
        try:
            result = subprocess.run(
                ["convert", "-delay", "1", *origin_frames, name + ".gif"],
                capture_output=True,
                text=True,
            )
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print(result.stderr)
        except FileNotFoundError:
            print("`convert` (ImageMagick) not found; skipping .gif assembly")


if __name__ == "__main__":
    # Specify folder containing

    from spinharmony_studio.settings import example_data_dir

    data_folder = example_data_dir()

    spinplot_auto(data_folder)
