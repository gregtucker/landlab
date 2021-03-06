#! /usr/env/python
"""
oriented_raster_cts.py: simple raster Landlab cellular automaton, with 
cell-pair transitions that depend on orientation (vertical or horizontal)

This file defines the OrientedRasterCTS class, which is a sub-class of 
CellLabCTSModel that implements a simple, oriented, raster-grid
CA. Like its parent class, OrientedRasterCTS implements a continuous-time, 
stochastic, pair-based CA.

Created GT Sep 2014
"""
from __future__ import print_function

from numpy import zeros

from .celllab_cts import CellLabCTSModel
from ...grid import RasterModelGrid


_DEBUG = False

class OrientedRasterCTS(CellLabCTSModel):
    """
    Class OrientedRasterCTS implements an oriented raster CellLab-CTS model.
    
    Example
    -------
    >>> from landlab import RasterModelGrid
    >>> from landlab.components.cellular_automata.celllab_cts import Transition
    >>> from landlab.components.cellular_automata.oriented_raster_cts import OrientedRasterCTS

    >>> mg = RasterModelGrid(3, 4, 1.0)
    >>> nsd = {0 : 'yes', 1 : 'no'}
    >>> xnlist = []
    >>> xnlist.append(Transition((0,1,0), (1,1,0), 1.0, 'frogging'))
    >>> nsg = mg.add_zeros('node', 'node_state_grid')
    >>> orcts = OrientedRasterCTS(mg, nsd, xnlist, nsg)
    """
    def __init__(self, model_grid, node_state_dict, transition_list,
                 initial_node_states, prop_data=None, prop_reset_value=None):
        """
        RasterCTS constructor: sets number of orientations to 2 and calls
        base-class constructor.
        
        Parameters
        ----------
        model_grid : Landlab ModelGrid object
            Reference to the model's grid
        node_state_dict : dict
            Keys are node-state codes, values are the names associated with
            these codes
        transition_list : list of Transition objects
            List of all possible transitions in the model
        initial_node_states : array of ints (x number of nodes in grid)
            Starting values for node-state grid
        prop_data : array (x number of nodes in grid) (optional)
            Array of properties associated with each node/cell
        prop_reset_value : (scalar; same type as entries in prop_data) (optional)
            Default or initial value for a node/cell property (e.g., 0.0)
        """
        
        if _DEBUG:
            print('OrientedRasterCTS.__init__ here')

        # Make sure caller has sent the right grid type        
        if not isinstance(model_grid, RasterModelGrid):
            raise TypeError('model_grid must be a Landlab RasterModelGrid')
               
        # Define the number of distinct cell-pair orientations: here just 1,
        # because RasterLCA represents a non-oriented CA model.
        self.number_of_orientations = 2
        
        # Call the LandlabCellularAutomaton constructor to do the rest of
        # the initialization
        super(OrientedRasterCTS, self).__init__(model_grid, node_state_dict, 
            transition_list, initial_node_states, prop_data, prop_reset_value)
            
        if _DEBUG:
            print('ORCTS:')
            print(self.n_xn)
            print(self.xn_to)
            print(self.xn_rate)
        

    def setup_array_of_orientation_codes(self):
        """
        Creates and configures an array that contain the orientation code for 
        each active link (and corresponding cell pair).
        
        Parameters
        ----------
        (none)
        
        Returns
        -------
        (none)
        
        Creates
        -------
        self.active_link_orientation : 1D numpy array of ints
            Array of orientation codes for each cell pair (link)
        
        Notes
        -----
        This overrides the method of the same name in landlab_ca.py.
        """
        # Create array for the orientation of each active link
        self.link_orientation = zeros(self.grid.number_of_links, dtype=int)
    
        # Set its value according to the different in y coordinate between each
        # link's TO and FROM nodes (the numpy "astype" method turns the
        # resulting array into integer format)
        dy = (self.grid.node_y[self.grid.node_at_link_head] -
              self.grid.node_y[self.grid.node_at_link_tail])
        self.link_orientation = dy.astype(int)
        
        if _DEBUG:
            print(self.active_link_orientation)
            
            
if __name__=='__main__':
    import doctest
    doctest.testmod()
