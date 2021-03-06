import numpy as np
from numpy.testing import assert_array_equal
from nose import with_setup
from nose.tools import (assert_equal, assert_raises)
try:
    from nose.tools import assert_is
except ImportError:
    from landlab.testing.tools import assert_is

from landlab.grid import raster_funcs as rfuncs
from landlab import RasterModelGrid


def test_with_arrays():
    rmg = RasterModelGrid(4, 5, dx=2.0)

    coords = (np.array([1., -1.]), np.array([1., -1.]))
    assert_array_equal(rfuncs.is_coord_on_grid(rmg, coords),
                       np.array([True, False]))


def test_just_inside():
    rmg = RasterModelGrid(4, 5, dx=2.0)

    assert_equal(rfuncs.is_coord_on_grid(rmg, (0., 4.)), True)
    assert_equal(rfuncs.is_coord_on_grid(rmg, (8. - 1e-12, 4.)), True)
    assert_equal(rfuncs.is_coord_on_grid(rmg, (3., 0.)), True)
    assert_equal(rfuncs.is_coord_on_grid(rmg, (3., 6. - 1e-12)), True)


def test_just_outside():
    rmg = RasterModelGrid(4, 5, dx=2.0)

    assert_equal(rfuncs.is_coord_on_grid(rmg, (0. - 1e-12, 4.)), False)
    assert_equal(rfuncs.is_coord_on_grid(rmg, (8., 4.)), False)
    assert_equal(rfuncs.is_coord_on_grid(rmg, (3., 0. - 1e-12)), False)
    assert_equal(rfuncs.is_coord_on_grid(rmg, (3., 6.)), False)


def test_just_x():
    rmg = RasterModelGrid(4, 5, dx=2.0)
    assert_equal(rfuncs.is_coord_on_grid(rmg, (4., 1.e6), axes=(1, )), True)
    assert_equal(rfuncs.is_coord_on_grid(rmg, (-1., 1.), axes=(1, )), False)

