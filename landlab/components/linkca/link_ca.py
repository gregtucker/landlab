#! /usr/env/python
"""
Link-based cellular automaton modeling tools.

In this updated version of the code, link states can either be encoded by
integer IDs, e.g., 0,1,2..., or tuples actually decribing the state, e.g.,
(x,y,0) to represent a horizontal link between x and y, 
(w,z,1) a vertical link between w and z (w below).
This change remains fully back compatible with GT's original version.

Created GT Oct 2013, modified DEJH Aug 2014 to optionally use identifying pair 
tuples, not just arbitrary IDs.
"""
from __future__ import print_function

from heapq import heappush
from heapq import heappop
from landlab import RasterModelGrid
import landlab
import numpy
#from landlab.plot import imshow_grid
import pylab as plt
import time

_NEVER = 1e12

_DEBUG = False

_TEST = False


class Transition():
    """
    Represents a transition from one state ("from_state") to another 
    ("to_state") at a link. The transition probability is represented by a rate 
    parameter "rate", with dimensions of 1/T. The probability distribution of 
    time until the transition event occurs is exponentional with mean 1/rate. 
    The optional name parameter allows the caller to assign a name to any given 
    transition.
    Note that from_state and to_state can now be either integer IDs for the
    standardised ordering of the link states (as before), or tuples explicitly
    describing the node state at each end, and the orientation.
    Orientation is 0: horizontal, L-R; 1: vertical, bottom-top.
    For such a tuple, order is (left/bottom, right/top, orientation).
    """
    def __init__(self, from_state, to_state, rate, name=None):
        
        self.from_state = from_state
        self.to_state = to_state
        self.rate = rate
        self.name = name
        
        
class Event():
    """
    Represents a transition event at a link. The transition occurs at a given
    link and a given time, and it involves a transition into the state xn_to
    (an integer code representing the new link state; "xn" is shorthand for
    "transition").
    
    The class overrides the __lt__ (less than operator) method so that when
    Event() objects are placed in a PriorityQueue, the earliest event is
    given the highest priority (i.e., placed at the top of the queue).
    
    Examples
    --------
    >>> from landlab.components.linkca.link_ca import Event
    >>> e1 = Event( 10.0, 1, 2)
    >>> e2 = Event( 2.0, 3, 1)
    >>> e1 < e2
    False
    >>> e2 < e1
    True
    """
    def __init__(self, time, link, xn_to):

        self.time = time
        self.link = link
        self.xn_to = xn_to
        
    def __lt__(self, other):
        
        return self.time < other.time
            
            
class CAPlotter():
    
    def __init__(self, ca):
        
        self.ca = ca
        
        plt.ion()
        plt.figure(1)
        #nsr=ca.grid.node_vector_to_raster(ca.node_state)
        #plt.imshow(nsr, interpolation='None')
        #plt.draw()
        #plt.pause(0.01)

    def update_plot(self):

        plt.clf()
        nsr = self.ca.grid.node_vector_to_raster(self.ca.node_state)
        plt.imshow(nsr, interpolation='None', origin='lower')
        plt.draw()
        plt.pause(0.01)
        
    def finalize(self):
        
        plt.ioff()
        plt.show()
        
        
class LinkCellularAutomaton():
    """
    The LinkCellularAutomaton implements a link-type (or doublet-type) cellular
    automaton model. A link connects a pair of cells. Each cell has a state
    (represented by an integer code), and each link also has a state that is
    determined by the states of the cell pair.
    """
    def __init__(self, model_grid, node_state_dict, transition_list,
                 initial_node_states, orientation_matters=False):
                 
        # Keep a copy of the model grid
        assert (type(model_grid) is landlab.grid.raster.RasterModelGrid), \
               'model_grid must be a Landlab RasterModelGrid'
        self.grid = model_grid
        self.node_active_links = self.grid.active_node_links()

        self.set_node_state_grid(initial_node_states)
        
        self.current_time = 0.0
        
        #a flag for the creation of link arrays needed to handle grid updates:
        self.translation_index = False
        
        # Figure out how many states there are, and make sure the input data
        # are self consistent.
        #   There are 2 x (N^2) link states, where N is the number of node 
        # states. For example, if there are just two node states, 0 and 1, then 
        # the possible oriented link pairs are listed below:
        #   0-0 0-1 1-0 1-1  0 0 1 1
        #                    0 1 0 1
        self.num_node_states = len(node_state_dict)
        self.num_link_states = 2*self.num_node_states*self.num_node_states  # VARIES WITH LATTICE AND ORIENTATION CHOICE
        
        assert (type(transition_list) is list), 'transition_list must be a list!'
        assert (transition_list), \
               'Transition list must contain at least one transition'
        last_type = None
        for t in transition_list:
            try:
                assert (t.from_state < self.num_link_states), \
                    'Transition from_state out of range'
                assert (t.to_state < self.num_link_states), \
                    'Transition to_state out of range'
                this_type = int
            except: #added to allow from and to states to be tuples, not just ids
                assert type(t.from_state) == tuple, 'Transition from_state out of range'
                assert type(t.to_state) == tuple, 'Transition to_state out of range'
                for i in t.from_state[:-1]:
                    assert (i < self.num_node_states), \
                    'Transition from_state out of range'
                for i in t.to_state[:-1]:
                    assert (i < self.num_node_states), \
                    'Transition to_state out of range'
                assert t.from_state[-1] < 2, \
                    'Encoding for horizontal/vertical in from_state must be 0 or 1.' # VARIES WITH LATTICE AND ORIENTATION CHOICE
                assert t.to_state[-1] < 2, \
                    'Encoding for horizontal/vertical in to_state must be 0 or 1.'
                this_type = tuple
            assert last_type==this_type or last_type==None, \
                'All transition types must be either int IDs, or all tuples.'
            #this test to ensure all entries are either IDs, or tuples, not mixed
            last_type=this_type
        
        # Create priority queue for events and next_update array for links
        self.event_queue = []
        self.next_update = self.grid.create_active_link_array_zeros()
    
        # Assign link types from node types
        self.create_link_state_dict_and_pair_list()

        #DEJH adds: convert transition_list to IDs if necessary
        #This is the new part that allows Transition from_ and to_ types 
        #to be specified either as ints, or as tuples.
        transition_list_as_ID = transition_list[:]
        if type(transition_list[0].from_state) == tuple:
            #(then they all are..., because of the assertions in __init__)
            for i in range(len(transition_list)):
                transition_list_as_ID[i].from_state = self.link_state_dict[transition_list[i].from_state]
                transition_list_as_ID[i].to_state = self.link_state_dict[transition_list[i].to_state]
    
        # Memorize the number of vertical links, so we can figure out
        # node-pair orientations
        # VARIES WITH LATTICE AND ORIENTATION CHOICE
        self.number_of_vertical_links = self.grid.number_of_node_columns * \
                                        (self.grid.number_of_node_rows-1)

        # Using the grid of node states, figure out all the link states
        self.assign_link_states_from_node_types()
    
        # Create transition data for links
        self.setup_transition_data(transition_list_as_ID)

        # Put the various transitions on the event queue
        self.push_transitions_to_event_queue()
        

    def set_node_state_grid(self, node_states):
        """
        Sets the grid of node-state codes to node_states. Also checks
        to make sure node_states is in the proper format, which is to
        say, it's a Numpy array of the same length as the number of nodes in 
        the grid.
        
        Creates: self.node_state (1D Numpy array)
        """
        assert (type(node_states) is numpy.ndarray), \
               'initial_node_states must be a Numpy array'
        assert (len(node_states)==self.grid.number_of_nodes), \
               'length of initial_node_states must equal number of nodes in grid'
        self.grid.at_node['node_state'] = node_states
        self.node_state = node_states
        
                 
    def create_link_state_dict_and_pair_list(self):
        """
        Creates a dictionary that can be used as a lookup table to find out 
        which link state corresponds to a particular pair of node states. The 
        dictionary keys are 3-element tuples, each of which represents the state
        of the FROM node, the TO node, and the orientation of the link. The 
        values are integer codes representing the link state numbers.
        """
        self.link_state_dict = {}
        self.cell_pair = []
        k=0
        for orientation in range(2):   # VARIES WITH LATTICE AND ORIENTATION CHOICE
            for fromstate in range(self.num_node_states):
                for tostate in range(self.num_node_states):
                    self.link_state_dict[(fromstate,tostate,orientation)] = k
                    k+=1
                    self.cell_pair.append((fromstate,tostate,orientation))
    
        if False and _DEBUG:
            print() 
            print('create_link_state_dict_and_pair_list(): dict is:')
            print(self.link_state_dict)
            print('  and the pair list is:')
            print(self.cell_pair)


    def active_link_orientation(self, act_link_id):
        """
        Returns 0 if active link *act_link_id* is horizontal (oriented along 
        x-axis), and 1 if it is vertical (oriented along y-axis).
        """
        # VARIES WITH LATTICE AND ORIENTATION CHOICE
        if self.grid.active_links[act_link_id]<self.number_of_vertical_links:
            return 1
        else:
            return 0
    
    
    def assign_link_states_from_node_types(self):
        """
        Assigns a link-state code for each link, and returns a list of these.
        
        Takes lists/arrays of "from" and "to" node IDs for each link, and a 
        dictionary that associates pairs of node states (represented as a 
        3-element tuple, comprising the FROM state, TO state, and orientation) 
        to link states.
        """
        self.link_state = numpy.zeros(self.grid.number_of_active_links,
                                      dtype=int)
    
        for i in range(self.grid.number_of_active_links):
            orientation = self.active_link_orientation(i)  # VARIES WITH LATTICE AND ORIENTATION CHOICE
            node_pair = (self.node_state[self.grid.activelink_fromnode[i]], \
                         self.node_state[self.grid.activelink_tonode[i]], \
                         orientation)
            #print 'node pair:', node_pair, 'dict:', self.link_state_dict[node_pair]
            self.link_state[i] = self.link_state_dict[node_pair]
        
        if False and _DEBUG:
            print() 
            print('assign_link_states_from_node_types(): the link state array is:')
            print(self.link_state)


    def setup_transition_data(self, xn_list):
        """
        Using the transition list and the number of link states, creates 
        three arrays that collectively contain data on state transitions:
            n_xn: for each link state, contains the number of transitions out of 
                  that state.
            xn_to: 2D array that records, for each link state and each
                   transition, the new state into which the link transitions.
            xn_rate: 2D array that records, for each link state and each
                     transition, the rate (1/time) of the transition.                 
        """
        # First, create an array that stores the number of possible transitions
        # out of each state.
        self.n_xn = numpy.zeros(self.num_link_states, dtype=int)
        for xn in xn_list:
            self.n_xn[xn.from_state] += 1
        
        # Now, create arrays to hold the "to state" and transition rate for each
        # transition. These arrays are dimensioned N x M where N is the number
        # of states, and M is the maximum number of transitions from a single 
        # state (for example if state 3 could transition either to state 1 or 
        # state 4, and the other states only had one or zero possible 
        # transitions, then the maximum would be 2).
        max_transitions = numpy.max(self.n_xn)
        self.xn_to = numpy.zeros((self.num_link_states, max_transitions), dtype=int)
        self.xn_rate = numpy.zeros((self.num_link_states, max_transitions))
    
        #print n_xn, xn_to, xn_rate
    
        # Populate the "to" and "rate" arrays
        self.n_xn[:] = 0  # reset this and then re-do (inefficient but should work)
        for xn in xn_list:
            #print 'from:',xn.from_state,'to:',xn.to_state,'rate:',xn.rate
            from_state = xn.from_state
            self.xn_to[from_state][self.n_xn[from_state]] = xn.to_state
            self.xn_rate[from_state][self.n_xn[from_state]] = xn.rate
            self.n_xn[from_state] += 1
    
        if False and _DEBUG:
            print() 
            print('setup_transition_data():')
            print('  n_xn',self.n_xn)
            print('  to:',self.xn_to)
            print('  rate:',self.xn_rate)
    
    
    def get_next_event(self, link, current_state, current_time):
        """
        Returns the next event for link with ID "link", which is in state
        "current state".
    
        If there is only one potential transition out of the current state, a 
        time for the transition is selected at random from an exponential 
        distribution with rate parameter appropriate for this transition.
    
        If there are more than one potential transitions, a transition time is 
        chosen for each, and the smallest of these applied.
    
        Assumes that there is at least one potential transition from the current
        state.
    
        Inputs: link - ID of the link
                current_state - current state code for the link
                current_time - current time in simulation (i.e., time of event
                                just processed)
            
        Returns: an Event() object containing the time, link ID, and type of the
                next transition event at this link.
        """
        assert (self.n_xn[current_state]>0), \
               'must have at least one potential transition'
    
        #rate = self.xn_rate[current_state][0]
        #rate = xn_rate[current_state][0] * (_SURFACE - ...
    
        # Find next event time for each potential transition
        if self.n_xn[current_state]==1:
            xn = self.xn_to[current_state][0]
            next_time = numpy.random.exponential(1.0/self.xn_rate[current_state][0])
        else:
            next_time = _NEVER
            xn = None
            for i in range(self.n_xn[current_state]):
                this_next = numpy.random.exponential(1.0/self.xn_rate[current_state][i])
                if this_next < next_time:
                    next_time = this_next
                    xn = self.xn_to[current_state][i]
    
        # Create and setup event, and return it
        my_event = Event(next_time+current_time, link, xn)
    
        if _DEBUG:
            print('get_next_event():')
            print('  next_time:',my_event.time)
            print('  link:',my_event.link)
            print('  xn_to:',my_event.xn_to)
    
        return my_event
    
    
    def push_transitions_to_event_queue(self):
    
        if False and _DEBUG:
            print('push_transitions_to_event_queue():',self.num_link_states,self.n_xn)
        for i in range(self.grid.number_of_active_links):
        
            #print i, self.link_state[i]
            if self.n_xn[self.link_state[i]] > 0:
                #print 'link',i,'has state',self.link_state[i],'and',self.n_xn[self.link_state[i]],'potential transitions'
                event = self.get_next_event(i, self.link_state[i], 0.0)
                heappush(self.event_queue, event)
                self.next_update[i] = event.time
            
            else:
                self.next_update[i] = _NEVER
            
        if True and _DEBUG:
            print('  push_transitions_to_event_queue(): events in queue are now:')
            for e in self.event_queue:
                print('    next_time:',e.time,'link:',e.link,'xn_to:',e.xn_to)
            
            
    def update_node_states(self, fromnode, tonode, new_link_state):
        """
        Updates the states of the two nodes in the given link.
        """
    
        # Remember the previous state of each node so we can detect whether the 
        # state has changed
        old_fromnode_state = self.node_state[fromnode]
        old_tonode_state = self.node_state[tonode]
    
        # Change to the new states
        if self.grid.node_status[fromnode]==landlab.grid.base.CORE_NODE:
            self.node_state[fromnode] = self.cell_pair[new_link_state][0]
        if self.grid.node_status[tonode]==landlab.grid.base.CORE_NODE:
            self.node_state[tonode] = self.cell_pair[new_link_state][1]
    
        if _DEBUG:
            print('update_node_states() for',fromnode,'and',tonode)
            print('  fromnode was',old_fromnode_state,'and is now',self.node_state[fromnode])
            print('  tonode was',old_tonode_state,'and is now',self.node_state[tonode])
    
        return self.node_state[fromnode]!=old_fromnode_state, \
               self.node_state[tonode]!=old_tonode_state
           
           
    def update_link_state(self, link, new_link_state, current_time):
        """
        Implements a link transition by updating the current state of the link
        and (if appropriate) choosing the next transition event and pushing it 
        on to the event queue.
    
        Inputs:
            link - ID of the link to update
            new_link_state - code for the new state
            current_time - current time in simulation
        """
        if _DEBUG:
            print()
            print('update_link_state()')
            
        # If the link connects to a boundary, we might have a different state
        # than the one we planned
        fn = self.grid.activelink_fromnode[link]
        tn = self.grid.activelink_tonode[link]
        if _DEBUG:
            print('fn',fn,'tn',tn,'fnstat',self.grid.node_status[fn],'tnstat',self.grid.node_status[tn])
        if self.grid.node_status[fn]!=landlab.grid.base.CORE_NODE or \
           self.grid.node_status[tn]!=landlab.grid.base.CORE_NODE:
            fns = self.node_state[self.grid.activelink_fromnode[link]]
            tns = self.node_state[self.grid.activelink_tonode[link]]
            orientation = self.active_link_orientation(link)  # VARIES WITH LATTICE AND ORIENTATION CHOICE
            actual_pair = (fns,tns,orientation)
            new_link_state = self.link_state_dict[actual_pair]
            if _DEBUG:
                print('**Boundary: overriding new link state to',new_link_state)
            
        self.link_state[link] = new_link_state
        if self.n_xn[new_link_state] > 0:
            event = self.get_next_event(link, new_link_state, current_time)
            heappush(self.event_queue, event)
            self.next_update[link] = event.time
        else:
            self.next_update[link] = _NEVER
            
        if _DEBUG:
            print()
            print('  at link',link)
            print('  state changed to',self.link_state[link],self.cell_pair[self.link_state[link]])
            print('  update time now',self.next_update[link])
        
            
    def do_transition(self, event, current_time, plot_each_transition=False,
                      plotter=None):
        """
        Implements a state transition. First checks that the transition is still
        valid by comparing the link's next_update time with the corresponding update
        time in the event object.
        
        If the transition is valid, we:
            1) Update the states of the two nodes attached to the link
            2) Update the link's state, choose its next transition, and push it on
            the event queue.
            3) Update the states of the other links attached to the two nodes, 
            choose their next transitions, and push them on the event queue.
            
        Inputs:
            event - Event() object containing the transition data.
            model_grid - ModelGrid() object
            node_state - array of states for each node
            next_update - time of next update for each link
            pair - list of node-state pairs corresponding to each link state
            link_state - array of states for each link
            n_xs - array with number of transitions out of each link state
            eq - event queue
            xn_rate - array with rate of each transition
            node_active_links - list of arrays containing IDs of links connected to
                each node
            ls_dict - dictionary of link-state codes corresponding to each 
                node-state pair
        
        """
    
        if _DEBUG:
            print()
            print('do_transition() for link',event.link)
            
        # We'll process the event if its update time matches the one we have 
        # recorded for the link in question. If not, it means that the link has
        # changed state since the event was pushed onto the event queue, and in that
        # case we'll ignore it.
        if event.time == self.next_update[event.link]:
        
            if _DEBUG:
                print('  event time =',event.time)
            
            fromnode = self.grid.activelink_fromnode[event.link]
            tonode = self.grid.activelink_tonode[event.link]
            from_changed, to_changed = self.update_node_states(fromnode, tonode, 
                                                          event.xn_to)
            self.update_link_state(event.link, event.xn_to, event.time)

            # Next, when the state of one of the link's nodes changes, we have to
            # update the states of the OTHER links attached to it. This could happen
            # to one or both nodes.
            if from_changed:
                
                if _DEBUG:
                    print('    fromnode has changed state, so updating its links')
            
                for link in self.node_active_links[:,fromnode]:
                    
                    if _DEBUG:
                        print('f checking link',link)
                    if link!=-1 and link!=event.link:
                    
                        this_link_fromnode = self.grid.activelink_fromnode[link]
                        this_link_tonode = self.grid.activelink_tonode[link]
                        orientation = self.active_link_orientation(link)# VARIES WITH LATTICE AND ORIENTATION CHOICE
                        current_pair = (self.node_state[this_link_fromnode], 
                                        self.node_state[this_link_tonode], orientation)
                        new_link_state = self.link_state_dict[current_pair]
                        self.update_link_state(link, new_link_state, event.time)

            if to_changed:
            
                if _DEBUG:
                    print('    tonode has changed state, so updating its links')
            
                for link in self.node_active_links[:,tonode]:
                
                    if _DEBUG:
                        print('t checking link',link)
                    if link!=-1 and link!=event.link:
                    
                        this_link_fromnode = self.grid.activelink_fromnode[link]
                        this_link_tonode = self.grid.activelink_tonode[link]
                        orientation = self.active_link_orientation(link)# VARIES WITH LATTICE AND ORIENTATION CHOICE
                        current_pair = (self.node_state[this_link_fromnode], 
                                        self.node_state[this_link_tonode], orientation)
                        new_link_state = self.link_state_dict[current_pair]
                        self.update_link_state(link, new_link_state, event.time)

            if plot_each_transition and (plotter is not None):
                plotter.update_plot()
                
            if _DEBUG:
                n = self.grid.number_of_nodes
                for r in range(self.grid.number_of_node_rows):
                    for c in range(self.grid.number_of_node_columns):
                        n -= 1
                        print('{0:.0f}'.format(self.node_state[n]), end=' ')
                    print()

        elif _DEBUG:
            print('  event time is',event.time,'but update time is', \
                  self.next_update[event.link],'so event will be ignored')
    
    def update_component_data(self, new_node_state_array, nodes_added, translation_vector, changed_uplift=False):
        """
        Call this method to update all data held by the component, if, for
        example, another component or boundary conditions modify the node 
        statuses outside the component between run steps.
        
        This method updates all necessary properties, including both node and
        link states.
        
        *new_node_state_array* is the updated list of node states, which must
        still all be compatible with the state list originally supplied to
        this component.
        *nodes_added* is a list or vector of nodes which have been added to the
        grid to effect uplift or deformation. This might typically be, e.g.,
        bottom_line_nodes[1:-1].
        *translation_vector* is a len 2 tuple describing the node offsets 
        associated with a single increment of deformation. e.g., (0,1) is unit
        uplift. (1,2) could be uplift on a normal fault dipping 60 degrees to
        the left.
        *changed_uplift* is a flag which tells the method to refresh its 
        stored parameters to reflect a step change in the uplift. Set as true
        if you change *nodes_added* or *translation_vector* during a model run.
        """
        self.set_node_state_grid(new_node_state_array)
        self.assign_link_states_from_node_types()
        self.push_transitions_to_event_queue()
        
        #we also need to update next_update
        if changed_uplift:
            self.translation_index = False
        #create the translation old & new lists if necessary (first time this is called)
        if self.translation_index is False:
            nrows = self.grid.number_of_node_rows
            ncols = self.grid.number_of_node_columns
            current_nodes = numpy.array(nodes_added[:])
            next_nodes = numpy.array(nodes_added[:])
            old_nodes = []
            new_nodes = []
            if translation_vector[0]>0:
                hoz_iter = (nrows-1-nodes_added%ncols)//translation_vector[0]
            elif translation_vector[0]<0:
                hoz_iter = (nodes_added%ncols)//-translation_vector[0]
            else:
                hoz_iter = None
            if translation_vector[1]>0:
                vert_iter = (ncols-1-nodes_added//ncols)//translation_vector[1]
            elif translation_vector[1]<0:
                vert_iter = (nodes_added//ncols)//-translation_vector[1]
            else:
                vert_iter = None
            try:
                max_iter = int(max((hoz_iter.max(),vert_iter.max())))
            except AttributeError:
                if vert_iter is not None:
                    max_iter = vert_iter.max()
                    hoz_iter = numpy.ones_like(nodes_added)*numpy.iinfo(int).max
                elif hoz_iter is not None:
                    max_iter = hoz_iter.max()
                    vert_iter = numpy.ones_like(nodes_added)*numpy.iinfo(int).max
                else:
                    raise ValueError('Is uplift vector (0,0)...???')
            #print nodes_added
            #print hoz_iter
            #print vert_iter
            #print max_iter
            for i in xrange(max_iter):
                print("Building the lists... ", i)
                on_grid_nodes = numpy.logical_and(
                                            numpy.greater(hoz_iter,i),
                                            numpy.greater(vert_iter,i))
                #print on_grid_nodes
                next_nodes = current_nodes+nrows*translation_vector[1]+translation_vector[0]
                
                if numpy.any(on_grid_nodes):
                    old_nodes.extend(current_nodes[on_grid_nodes])
                    new_nodes.extend(next_nodes[on_grid_nodes])
                    current_nodes[on_grid_nodes] = next_nodes[on_grid_nodes]
                else:
                    break
            #print old_nodes
            old_links = self.grid.node_activelinks(old_nodes)
            new_links = self.grid.node_activelinks(new_nodes)
            print(old_links.shape)
            print(new_links.shape)
            self.old_links, unique_index = numpy.unique(old_links, return_index=True)
            self.new_links = new_links.flat[unique_index]
            self.translation_index = True
            self.links_refreshed = numpy.unique(self.grid.node_links(nodes_added))
            self.link_conversion_dict = dict(zip(self.old_links,self.new_links))
        
        self.next_update[self.new_links] = self.next_update[self.old_links]
        self.next_update[self.links_refreshed] = 0.
        for j in self.event_queue:
            try:
                j.link = self.link_conversion_dict[j.link]
            except KeyError:
                pass
        
                  
    def run(self, run_duration, node_state_grid=None, plot_each_transition=False,
            plotter=None):
        
        if node_state_grid is not None:
            self.set_node_state_grid(node_state_grid)
    
        # Continue until we've run out of either time or events
        while self.current_time < run_duration and self.event_queue:
        
            if _DEBUG:
                print('Current Time = ', self.current_time)
        
            # Pick the next transition event from the event queue
            ev = heappop(self.event_queue)
        
            if _DEBUG:
                print('Event:',ev.time,ev.link,ev.xn_to)
        
            self.do_transition(ev, self.current_time, plot_each_transition,
                               plotter)
            
            # Update current time
            self.current_time = ev.time

        
def example_test2():
    
    #from landlab.io.netcdf import write_netcdf
    
    # INITIALIZE

    # User-defined parameters
    nr = 128
    nc = 128
    plot_interval = 0.5
    #next_plot = plot_interval
    run_duration = 50.0
    report_interval = 5.0  # report interval, in real-time seconds
    
    # Initialize real time
    current_real_time = time.time()
    next_report = current_real_time + report_interval

    # Create grid and set up boundaries
    mg = RasterModelGrid(nr, nc, 1.0)
    #mg.set_inactive_boundaries(True, True, True, True)
    
    # Transition data here represent a body of fractured rock, with rock 
    # represented by nodes with state 0, and saprolite (weathered rock)
    # represented by nodes with state 1. Node pairs (links) with 0-1 or 1-0
    # can undergo a transition to 1-1, representing chemical weathering of the
    # rock.
    ns_dict = { 0 : 'air', 1 : 'immobile soil', 2 : 'mobile soil' }
    xn_list = setup_transition_list2()

    # The initial grid represents a domain with half immobile soil, half air
    node_state_grid = mg.add_zeros('node', 'node_state_map', dtype=int)
    if _DEBUG:
        print((numpy.where(mg.node_y<nr/2),))
    (lower_half,) = numpy.where(mg.node_y<nr/2)
    node_state_grid[lower_half] = 1
    
    # Set the left and right boundary conditions
    node_state_grid[mg.left_edge_node_ids()] = 0
    node_state_grid[mg.right_edge_node_ids()] = 0
    
    # Create the CA model
    ca = LinkCellularAutomaton(mg, ns_dict, xn_list, node_state_grid)
    
    print('INITIALIZING')
    n = ca.grid.number_of_nodes
    if _DEBUG:
        for r in range(ca.grid.number_of_node_rows):
            for c in range(ca.grid.number_of_node_columns):
                n -= 1
                print('{0:.0f}'.format(ca.node_state[n]), end=' ')
            print()
        
    ca_plotter = CAPlotter(ca)
    
    # RUN
    current_time = 0.0
    #time_slice =  0
    #filename = 'soil_ca1-'+str(time_slice).zfill(5)+'.nc'
    #write_netcdf(filename, ca.grid)
    while current_time < run_duration:
        
        # Once in a while, print out simulation and real time to let the user
        # know that the sim is running ok
        current_real_time = time.time()
        if current_real_time >= next_report:
            print('Current sim time',current_time,'(',100*current_time/run_duration,'%)')
            next_report = current_real_time + report_interval
        
        ca.run(current_time+plot_interval, ca.node_state, 
               plot_each_transition=False) #, plotter=ca_plotter)
        current_time += plot_interval
        if _DEBUG:
            print('time:',current_time)
            print('ca time:',ca.current_time)
        ca_plotter.update_plot()
        #time_slice += 1
        #filename = 'soil_ca1-'+str(time_slice).zfill(5)+'.nc'
        #write_netcdf(filename, ca.grid)
        if _DEBUG:
            n = ca.grid.number_of_nodes
            for r in range(ca.grid.number_of_node_rows):
                for c in range(ca.grid.number_of_node_columns):
                    n -= 1
                    print('{0:.0f}'.format(ca.node_state[n]), end=' ')
                print()
        
        
    # FINALIZE
    
    # Plot
    ca_plotter.finalize()
        
        
def setup_transition_list():
    """
    Creates and returns a list of Transition() objects. This is a "custom"
    function in the sense that any particular application is determined by the
    transition rules that are created here.
    """
    xn_list = []
    
    xn_list.append( Transition(1, 3, 1., 'weathering') ) # rock-sap to sap-sap
    xn_list.append( Transition(2, 3, 1., 'weathering') ) # sap-rock to sap-sap
        
    if False and _DEBUG:
        print()
        print('setup_transition_list(): list has',len(xn_list),'transitions:')
        for t in xn_list:
            print('  From state',t.from_state,'to state',t.to_state,'at rate',t.rate,'called',t.name)
        
    return xn_list
    
    
def setup_transition_list2():
    """
    This one is a crude model of "sticky" particles on a gravity-free hill!
    
    There are three cell states: air (A=0), immobile soil (S=1), and mobile
    soil (M=2)
    
    The transition rules are:
        
        1. Mobilization: A-S > A-M (all orientations equal)
        2. Motion: A-M > M-A (")
        3. Sticking: A-M > A-S (")

    Example of link states associated with 3 node states (0, 1, and 2):
    
    Link states with "horizontal" orientation:

    State:    Pair:  
    0            0-0
    1            0-1
    2            0-2
    3            1-0
    4            1-1
    5            1-2
    6            2-0
    7            2-1
    8            2-2

    Link states with "vertical" orientation (the first number in each pair is
    the lower of the two, i.e., the one with the smaller y coordinate):
    
    State:    Pair:  
    9            0^0
    10           0^1
    11           0^2
    12           1^0
    13           1^1
    14           1^2
    15           2^0
    16           2^1
    17           2^2
   
    """
    xn_list = []
    
    xn_list.append( Transition(1, 2, 1., 'mobilization') ) # 
    xn_list.append( Transition(3, 6, 1., 'mobilization') ) # 
    xn_list.append( Transition(10, 11, 1., 'mobilization') ) # 
    xn_list.append( Transition(12, 15, 1., 'mobilization') ) # 
    xn_list.append( Transition(2, 6, 10., 'left motion') )
    xn_list.append( Transition(6, 2, 10., 'right motion') )
    xn_list.append( Transition(11, 15, 1000., 'downward motion') )
    xn_list.append( Transition(15, 11, 1.0, 'upward motion') )    
        
    if False and _DEBUG:
        print()
        print('setup_transition_list2(): list has',len(xn_list),'transitions:')
        for t in xn_list:
            print('  From state',t.from_state,'to state',t.to_state,'at rate',t.rate,'called',t.name)
        
    return xn_list
    
    
if __name__ == "__main__":
    import doctest
    doctest.testmod()
    #main()
