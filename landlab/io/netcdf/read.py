#! /usr/bin/env python
"""
Read data from a NetCDF file into a RasterModelGrid.
"""

try:
    import netCDF4 as nc4
except ImportError:
    import warnings
    warnings.warn('Unable to import netCDF4.', ImportWarning)

from scipy.io import netcdf as nc

import os
import types
import re

import numpy as np

from landlab.io.netcdf.errors import NotRasterGridError
from landlab.io.netcdf._constants import (_AXIS_DIMENSION_NAMES,
                                          _AXIS_COORDINATE_NAMES,
                                          _COORDINATE_NAMES)


def _length_of_axis_dimension(root, axis_name):
    try:
        return len(root.dimensions[axis_name])
    except TypeError:
        return root.dimensions[axis_name]


def _read_netcdf_grid_shape(root):
    shape = []
    for axis_name in _AXIS_DIMENSION_NAMES:
        try:
            shape.append(_length_of_axis_dimension(root, axis_name))
        except KeyError:
            pass
    return shape


def _read_netcdf_coordinate_values(root):
    values = []
    for coordinate_name in _AXIS_COORDINATE_NAMES:
        try:
            values.append(root.variables[coordinate_name][:].copy())
        except KeyError:
            pass
    return values


def _read_netcdf_coordinate_units(root):
    units = []
    for coordinate_name in _AXIS_COORDINATE_NAMES:
        try:
            units.append(root.variables[coordinate_name].units)
        except KeyError:
            pass
    return units


def _read_netcdf_structured_grid(root):
    shape = _read_netcdf_grid_shape(root)
    coordinates = _read_netcdf_coordinate_values(root)
    units = _read_netcdf_coordinate_units(root)

    for coordinate in coordinates:
        coordinate.shape = shape

    return coordinates


def _read_netcdf_structured_data(root):
    fields = dict()
    for (name, var) in root.variables.items():
        if not name in _COORDINATE_NAMES:
            fields[name] = var[:].copy()
            fields[name].shape = (fields[name].size, )
    return fields


def _get_raster_spacing(coords):
    spacing = np.empty(len(coords), dtype=np.float64)

    for (axis, coord) in enumerate(coords):
        coord_spacing = np.diff(coord, axis=axis)
        try:
            assert(np.all(coord_spacing == coord_spacing.flat[0]))
        except AssertionError:
            raise NotRasterGridError()
        spacing[axis] = coord_spacing.flat[0]

    try:
        assert(np.all(spacing == spacing[0]))
    except AssertionError:
        raise NotRasterGridError()
    else:
        return spacing[0]


def read_netcdf(nc_file, just_grid=False):
    """Create a :class:`~.RasterModelGrid` from a netcdf file.

    Create a new :class:`~.RasterModelGrid` from the netcdf file, *nc_file*.
    If the netcdf file also contains data, add that data to the grid's fields.
    To create a new grid without any associated data from the netcdf file,
    set the *just_grid* keyword to ``True``.

    Parameters
    ----------
    nc_file : str
        Name of a netcdf file.
    just_grid : boolean, optional
        Create a new grid but don't add value data.

    Returns
    -------
    :class:`~.RasterModelGrid`
        A newly-created :class:`~.RasterModelGrid`.

    Examples
    --------
    Import :func:`read_netcdf` and the path to an example netcdf file included
    with landlab.

    >>> from landlab.io.netcdf import read_netcdf
    >>> from landlab.io.netcdf import NETCDF4_EXAMPLE_FILE

    Create a new grid from the netcdf file. The example grid is a uniform
    rectilinear grid with 4 rows and 3 columns of nodes with unit spacing.
    The data file also contains data defined at the nodes for the grid for
    a variable called, *surface__elevation*.

    >>> grid = read_netcdf(NETCDF4_EXAMPLE_FILE)
    >>> grid.shape == (4, 3)
    True
    >>> grid.node_spacing
    1.0
    >>> [str(k) for k in grid.at_node.keys()]
    ['surface__elevation']
    >>> grid.at_node['surface__elevation']
    array([  0.,   1.,   2.,   3.,   4.,   5.,   6.,   7.,   8.,   9.,  10.,
            11.])

    :func:`read_netcdf` will try to determine the format of the netcdf file.
    For example, the same call will also work for *netcdf3*-formatted files.

    >>> from landlab.io.netcdf import NETCDF3_64BIT_EXAMPLE_FILE
    >>> grid = read_netcdf(NETCDF3_64BIT_EXAMPLE_FILE)
    >>> grid.shape == (4, 3)
    True
    >>> grid.node_spacing
    1.0
    """
    from landlab import RasterModelGrid

    try:
        root = nc.netcdf_file(nc_file, 'r', version=2)
    except TypeError:
        root = nc4.Dataset(nc_file, 'r', format='NETCDF4')

    node_coords = _read_netcdf_structured_grid(root)

    assert(len(node_coords) == 2)

    spacing = _get_raster_spacing(node_coords)

    shape = node_coords[0].shape

    grid = RasterModelGrid(num_rows=shape[0], num_cols=shape[1],
                           dx=spacing)

    if not just_grid:
        fields = _read_netcdf_structured_data(root)
        for (name, values) in fields.items():
            grid.add_field('node', name, values)

    root.close()

    return grid
