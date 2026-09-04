"""A script to convert the output of spinvert into a suitable
format for spindist and spinplot and then generates input files
calls spindist and spinplot and generates stereographics projections

THIS ONLY WORKS ON HEISEINBERG SPINS!!!!

"""

import os

import numpy as np

from spinharmony_studio.settings import (
    example_data_dir,
    load_spindist_path,
    load_spinplot_path,
)
from spinharmony_studio.spinvert.config import SpinvertConfig


def spinplot_auto(data_location: str, nphi: int = 40, ntheta: int = 40) -> None:
    """Thius script takes the output of spinvert and converts it into a suitable format
    for spindist and spinplot. It then generates input files,
    calls spindist and spinplot, and generates stereographic projections."""

    config_file = [f for f in os.listdir(data_location) if f.endswith("_config.txt")][0]

    spinvert_config = SpinvertConfig.from_file(os.path.join(data_location, config_file))

    if spinvert_config.spin_dimension != 3:
        raise ValueError(
            "Spinvert config file does not have spin dimension of 3. "
            "This script only works for Heisenberg spins."
        )

    # Specify location of spindist and spinplot
    spindist_location = load_spindist_path()
    spinplot_location = load_spinplot_path()

    if spindist_location is None or spinplot_location is None:
        raise FileNotFoundError(
            "spindist and/or spinplot executable not found. Please set the paths in settings.py"  # noqa
        )

    # Title of file
    data_file_name = [f for f in os.listdir(data_location) if f.endswith("_data.txt")]

    name = data_file_name[0].replace("_data.txt", "")

    # How many different unique element magnetic ions are in our unit cell?
    number_of_magnetic_ions = len(spinvert_config.sites)

    # Spindist paramters
    value_of_nphi = nphi
    value_of_ntheta = ntheta
    rotation_matrix = "n"
    suffix = "_spinplot.txt"
    spindist_outputname = name + "_spindist.txt"
    input_spindist_name = "input_spindist.txt"

    # Get a list of files in folder that are a text file
    data_file_list = [f for f in os.listdir(data_location) if f.endswith(".txt")]
    # Filter list to give files that a only _spins_xx.txt files that contain spin
    # vectors and box information that are to be converted (where xx is integer) etc
    letters = "_spins"
    spins_data_list = []
    for data_file in data_file_list:
        if letters in data_file:
            spins_data_list.append(data_file)
    spins_data_list.sort()
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
            data, skip_header=19, usecols=[1, 2, 3, 4, 5, 6, 7], unpack=True
        )
        # stacks the x,y and z scalar to produce a vector for each ion
        spin_vector = np.stack((x_spin_scalar, y_spin_scalar, z_spin_scalar), axis=1)
        # spin_box = np.stack((box_x_coor, box_y_coor, box_z_coor), axis=1)
        # creates suitable data name and location
        new_data_name = os.path.splitext(data_name)[-2]
        new_data_name = new_data_name.replace(letters, "")
        new_data_name = new_data_name + "_spinplot.txt"
        new_data_name = os.path.join(data_location, new_data_name)

        # stack the spins, and the spin numbers of the separate files into
        # a list for later concatenation into 1 file
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
    os.system(spindist_location + "<" + input_spindist_name)

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

    os.system(spinplot_location + "<" + input_spinplot_origin)

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

    os.system(spinplot_location + "<" + input_spinplot_top)

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

    os.system(spinplot_location + "<" + input_spinplot_bottom)

    print("Spinplot bottom complete")

    try:
        os.system("convert -delay 1 *origin.ppm " + name + ".gif")
    except Exception as e:
        print(f"Error occurred while creating GIF: {e}")


if __name__ == "__main__":
    data_folder = str(example_data_dir())
    spinplot_auto(data_folder)
