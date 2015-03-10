from awesome_tool.utils import log
from awesome_tool.utils.geometry import point_in_triangle, dist, point_on_line

logger = log.get_logger(__name__)
import sys
import time
from awesome_tool.statemachine.enums import StateType
from awesome_tool.mvc.controllers.extended_controller import ExtendedController
from awesome_tool.mvc.models import ContainerStateModel, StateModel, TransitionModel, DataFlowModel
from awesome_tool.mvc.models.state_machine import StateMachineModel
from awesome_tool.mvc.statemachine_helper import StateMachineHelper
from gtk.gdk import SCROLL_DOWN, SCROLL_UP, SHIFT_MASK, CONTROL_MASK
from gtk.gdk import keyval_name
from awesome_tool.statemachine.states.concurrency_state import ConcurrencyState
from awesome_tool.mvc.models.scoped_variable import ScopedVariableModel
from awesome_tool.mvc.models.data_port import DataPortModel


class GraphicalEditorController(ExtendedController):
    """Controller handling the graphical editor

    :param awesome_tool.mvc.models.ContainerStateModel model: The root container state model containing the data
    :param awesome_tool.mvc.views.GraphicalEditorView view: The GTK view having an OpenGL rendering element
    """

    def __init__(self, model, view):
        """Constructor
        """
        assert isinstance(model, StateMachineModel)
        ExtendedController.__init__(self, model, view)
        self.root_state_m = model.root_state

        self.selection = None
        self.selection_start_pos = (0, 0)
        self.mouse_move_start_coords = (0, 0)
        self.last_button_pressed = -1
        self.drag_origin_offset = None

        self.selected_outcome = None
        self.selected_port = None
        self.selected_waypoint = None
        self.selected_resizer = None

        self.shift_modifier = False
        self.alt_modifier = False
        self.ctrl_modifier = False

        view.editor.connect('expose_event', self._on_expose_event)
        view.editor.connect('button-press-event', self._on_mouse_press)
        view.editor.connect('button-release-event', self._on_mouse_release)
        # Only called when the mouse is clicked while moving
        view.editor.connect('motion-notify-event', self._on_mouse_motion)
        view.editor.connect('scroll-event', self._on_scroll)
        view.editor.connect('key-press-event', self._on_key_press)
        view.editor.connect('key-release-event', self._on_key_release)
        self.last_time = time.time()

    def register_view(self, view):
        """Called when the View was registered
        """
        pass

    def register_adapters(self):
        """Adapters should be registered in this method call
        """
        pass

    def register_actions(self, shortcut_manager):
        """Register callback methods for triggered actions

        :param awesome_tool.mvc.shortcut_manager.ShortcutManager shortcut_manager:
        """
        shortcut_manager.add_callback_for_action("delete", self._delete_selection)
        shortcut_manager.add_callback_for_action("add", self._add_execution_state)

    @ExtendedController.observe("state_machine", after=True)
    def state_machine_change(self, model, prop_name, info):
        """Called on any change within th state machine

        This method is called, when any state, transition, data flow, etc. within the state machine changes. This
        then typically requires a redraw of the graphical editor, to display these changes immediately.
        :param model: The state machine model
        :param prop_name: The property that was changed
        :param info: Information about the change
        """
        if 'method_name' in info and info['method_name'] == 'root_state_after_change':
            logger.debug("Change in SM, redraw...")
            self._redraw(True)

    @ExtendedController.observe("root_state", after=True)
    def root_state_change(self, model, prop_name, info):
        """Called when the root state was exchanged

        Exchanges the local reference to the root state and redraws
        :param model: The state machine model
        :param prop_name: The root state
        :param info: Information about the change
        """
        if self.root_state_m is not model.root_state:
            logger.debug("The root state was exchanged")
            self.root_state_m = model.root_state
            self._redraw(True)


    @ExtendedController.observe("selection", after=True)
    def selection_change(self, model, prop_name, info):
        """Called when the selection was changed externally

        Updates the local selection and redraws
        :param model: The state machine model
        :param prop_name: The selection
        :param info: Information about the change
        """
        selection = None
        for selection in self.model.selection:
            pass
        if self.selection != selection:
            self.selection = selection
            self._redraw(True)

    def _on_expose_event(self, *args):
        """Redraw the graphical editor

        This method is called typically when the editor window is resized or something triggers are redraw. This
        controller class handles the logic for redrawing, while the corresponding view handles the design.
        :param args: console arguments, not used
        """

        # Prepare the drawing process
        self.view.editor.expose_init(args)
        # The whole logic of drawing is triggered by calling the root state to be drawn
        self.draw_state(self.root_state_m)
        # Finish the drawing process (e.g. swap buffers)
        self.view.editor.expose_finish(args)

    def _redraw(self, important=False):
        """Force the graphical editor to be redrawn

        First triggers the configure event to cause the perspective to be updated, then trigger the actual expose
        event to redraw.
        """
        # Check if initialized
        if hasattr(self.view, "editor") and (time.time() - self.last_time > 1 / 50. or important):
            self.view.editor.emit("configure_event", None)
            self.view.editor.emit("expose_event", None)
            self.last_time = time.time()

    def _on_key_press(self, widget, event):
        key_name = keyval_name(event.keyval)
        # print "key press", key_name
        if key_name == "Control_L" or key_name == "Control_R":
            self.ctrl_modifier = True
        elif key_name == "Alt_L":
            self.alt_modifier = True
        elif key_name == "Shift_L" or key_name == "Shift_R":
            self.shift_modifier = True

    def _on_key_release(self, widget, event):
        key_name = keyval_name(event.keyval)
        # print "key release", key_name
        if key_name == "Control_L" or key_name == "Control_R":
            self.ctrl_modifier = False
        elif key_name == "Alt_L":
            self.alt_modifier = False
        elif key_name == "Shift_L" or key_name == "Shift_R":
            self.shift_modifier = False

    def _on_mouse_press(self, widget, event):
        """Triggered when the mouse is pressed

        Different actions can result from a mouse click, e. g. selecting or drag and drop
        :param widget: The widget beneath the mouse when the click was done
        :param event: Information about the event, e. g. x and y coordinate
        """

        self.last_button_pressed = event.button
        self.selected_waypoint = None  # reset
        self.selected_outcome = None  # reset
        self.selected_port = None  # reset
        self.selected_resizer = None  # reset

        # Store the coordinates of the event
        self.mouse_move_start_coords = self.view.editor.screen_to_opengl_coordinates((event.x, event.y))
        self.mouse_move_last_pos = self.view.editor.screen_to_opengl_coordinates((event.x, event.y))

        # Left mouse button was clicked
        if event.button == 1:

            # Check if something was selected
            new_selection = self._find_selection(event.x, event.y)

            # Check whether a state, a transition or data flow was clicked on
            # If so, set the meta data of the object to "object selected" and redraw to highlight the object
            # If the object was previously selected, remove the selection
            if new_selection != self.selection:
                if self.selection is not None:
                    self.model.selection.clear()
                self.selection = new_selection
                if self.selection is not None:
                    self.model.selection.add(self.selection)
            # Add this if a click shell toggle the selection
            # else:
            # self.model.selection.clear()
            # self.selection = None

            # If a state was clicked on, store the original position of the selected state for a drag and drop movement
            if self.selection is not None and isinstance(self.selection, StateModel):
                self.selection_start_pos = (self.selection.meta['gui']['editor']['pos_x'],
                                            self.selection.meta['gui']['editor']['pos_y'])

            # Check, whether a waypoint was clicked on
            self._check_for_waypoint_selection(self.mouse_move_start_coords)

            # Check, whether an outcome was clicked on
            self._check_for_outcome_selection(self.mouse_move_start_coords)

            # Check, whether a port (input, output, scope) was clicked on
            self._check_for_port_selection(self.mouse_move_start_coords)

            # Check, whether a resizer was clicked on
            self._check_for_resizer_selection(self.mouse_move_start_coords)

            self._redraw(True)

        # Right mouse button was clicked on
        if event.button == 3:

            # Check if something was selected
            click = self.view.editor.screen_to_opengl_coordinates((event.x, event.y))
            clicked_model = self._find_selection(event.x, event.y)

            # If a connection (transition or data flow) was clicked
            if isinstance(clicked_model, TransitionModel) or isinstance(clicked_model, DataFlowModel):

                # If the right click was on a waypoint of a connection, the waypoint is removed
                waypoint_removed = self._check_for_waypoint_removal(click, clicked_model)

                # If no waypoint was removed, we want to add one at that position
                if not waypoint_removed:
                    self._add_waypoint(clicked_model, click)

    def _on_mouse_release(self, widget, event):
        """Triggered when a mouse button is being released

        :param widget: The widget beneath the mouse when the release was done
        :param event: Information about the event, e. g. x and y coordinate
        Not used so far
        """
        self.last_button_pressed = None
        self.drag_origin_offset = None
        mouse_position = (event.x, event.y)

        if self.selected_outcome is not None:
            self._create_new_transition(mouse_position)

        if self.selected_port is not None:
            self._create_new_data_flow(mouse_position)

    def _on_mouse_motion(self, widget, event):
        """Triggered when the mouse is moved while being pressed

        When a state is selected, this causes a drag and drop movement
        :param widget: The widget beneath the mouse when the click was done
        :param event: Information about the event, e. g. x and y coordinate
        """
        mouse_current_coord = self.view.editor.screen_to_opengl_coordinates((event.x, event.y))
        rel_x_motion = mouse_current_coord[0] - self.mouse_move_start_coords[0]
        rel_y_motion = mouse_current_coord[1] - self.mouse_move_start_coords[1]

        # Move while middle button is clicked moves the view
        if self.last_button_pressed == 2:
            self._move_view(rel_x_motion, rel_y_motion)

        # Translate the mouse movement to OpenGL coordinates
        new_pos_x = self.selection_start_pos[0] + rel_x_motion
        new_pos_y = self.selection_start_pos[1] + rel_y_motion

        # Move the selected state (if there is an appropriate one)
        if isinstance(self.selection, StateModel) and \
                        self.selection != self.root_state_m and \
                        self.last_button_pressed == 1 and \
                        self.selected_outcome is None and self.selected_port is None and \
                        self.selected_resizer is None:
            self._move_state(self.selection, new_pos_x, new_pos_y)

        # Move the selected waypoint (if there is one)
        if self.selected_waypoint is not None:
            # Move selected waypoint within its container state
            new_pos_x, new_pos_y = self._limit_position_to_state(self.selection.parent, new_pos_x, new_pos_y)
            self.selected_waypoint[0][self.selected_waypoint[1]] = (new_pos_x, new_pos_y)
            self._redraw()

        # Move data port
        if isinstance(self.selection, DataPortModel):
            self._move_data_port(self.selection, mouse_current_coord)

        # Redraw to show the new transition/data flow the user is creating with drag and drop
        if self.selected_outcome is not None or self.selected_port is not None:
            self._redraw()

        if self.selected_resizer is not None:
            modifier = event.state
            self._resize_state(self.selection, mouse_current_coord, rel_x_motion, rel_y_motion, modifier)

        self.mouse_move_last_pos = mouse_current_coord

    def _on_scroll(self, widget, event):
        """Triggered when the mouse wheel is turned

        Calls the zooming method.
        :param widget: The widget beneath the mouse when the event was triggered
        :param event: Information about the event, e. g. x and y coordinate and mouse wheel turning direction
        """
        self._handle_zooming((event.x, event.y), event.direction)

    @staticmethod
    def _limit_position_to_state(state, pos_x, pos_y, child_width=0, child_height=0):
        if state is not None:
            if pos_x < state.meta['gui']['editor']['pos_x']:
                pos_x = state.meta['gui']['editor']['pos_x']
            elif pos_x + child_width > state.meta['gui']['editor']['pos_x'] + state.meta['gui']['editor']['width']:
                pos_x = state.meta['gui']['editor']['pos_x'] + state.meta['gui']['editor']['width'] - child_width

            if pos_y < state.meta['gui']['editor']['pos_y']:
                pos_y = state.meta['gui']['editor']['pos_y']
            elif pos_y + child_height > state.meta['gui']['editor']['pos_y'] + state.meta['gui']['editor']['height']:
                pos_y = state.meta['gui']['editor']['pos_y'] + state.meta['gui']['editor']['height'] - child_height
        return pos_x, pos_y

    def _check_for_waypoint_selection(self, coords):
        """Check whether a waypoint was clicked on

        Checks whether the current selection is a transition or data flow and if so looks for a waypoint at the given
        coordinates. If a waypoint is found, it is stored together with its current position.
        :param coords: Coordinates to search for waypoints
        """
        if self.selection is not None and \
                (isinstance(self.selection, TransitionModel) or isinstance(self.selection, DataFlowModel)):
            close_threshold = min(self.selection.parent.meta['gui']['editor']['height'],
                                  self.selection.parent.meta['gui']['editor']['width)']) / 50.

            # Check distance between all waypoints of the selected transition/data flows and the given coordinates
            for i, waypoint in enumerate(self.selection.meta['gui']['editor']['waypoints']):
                # Only if coordinates are stored for the waypoints (always should be the case)
                if waypoint[0] is not None and waypoint[1] is not None:
                    if dist(waypoint, coords) < close_threshold:
                        # As tuples cannot be changed, we have to store the whole list plus the index
                        self.selected_waypoint = (self.selection.meta['gui']['editor']['waypoints'], i)
                        self.selection_start_pos = (waypoint[0], waypoint[1])
                        break

    def _check_for_outcome_selection(self, coords):
        """Check whether a port was clicked on

        Checks whether the current selection is a state and if so looks for an outcome at the given coordinates. If an
        outcome is found, it is stored.
        :param coords: Coordinates to search for outcomes
        """
        if self.selection is not None and isinstance(self.selection, StateModel) and \
                        self.selection is not self.root_state_m:
            outcomes_close_threshold = self.selection.meta['gui']['editor']['outcome_radius']
            outcomes = self.selection.meta['gui']['editor']['outcome_pos']
            # Check distance between all outcomes of the selected state and the given coordinate
            for key in outcomes:
                if dist(outcomes[key], coords) < outcomes_close_threshold:
                    self.selected_outcome = (outcomes, key)

    def _check_for_port_selection(self, coords):
        """Check whether a port was clicked on

        Checks whether the current selection is a state and if so looks for a port at the given coordinates. If a
        port is found, it is stored.
        :param coords: Coordinates to search for ports
        """
        if self.selection is not None and isinstance(self.selection, StateModel):
            connectors_close_threshold = self.selection.meta['gui']['editor']['port_radius']
            # Look up all port coordinates of the selected state
            connectors = dict(self.selection.meta['gui']['editor']['input_pos'].items() +
                              self.selection.meta['gui']['editor']['output_pos'].items() +
                              self.selection.meta['gui']['editor']['scoped_pos'].items())
            # Check distance of all port coordinates to the given coordinate
            for key in connectors:
                if dist(connectors[key], coords) < connectors_close_threshold:
                    self.selected_port = (self.selection, key)

    def _check_for_resizer_selection(self, coords):
        """Check whether a resizer (handle to resize a state) was clicked on

        Checks whether the current selection is a state and if so looks the given coordinates are within the resizer
        of that state. If so, the resizer (or its state model) is stored.
        :param coords: Coordinates to check for the resizer
        """
        if self.selection is not None and isinstance(self.selection, StateModel) and self.selection:
            state_editor_data = self.selection.meta['gui']['editor']
            # Calculate corner points of resizer
            p1 = (state_editor_data['pos_x'] + state_editor_data['width'], state_editor_data['pos_y'])
            p2 = (p1[0] - state_editor_data['resize_length'], p1[1])
            p3 = (p1[0], p1[1] + state_editor_data['resize_length'])

            # The resizer is triangle. Check whether the given coordinates are within that triangle
            if point_in_triangle(coords, p1, p2, p3):
                self.selected_resizer = self.selection

    def _check_for_waypoint_removal(self, coords, connection_model):
        """Checks and removes a waypoint if necessary

        Checks whether the coordinates given are close to a waypoint of the given connection model (transition or
        data flow). If so, the waypoint is removed
        :param coords: Coordinates to check for a waypoint
        :param connection_model: Model of a transition or data flow
        :return: True, if a waypoint was removed, False else
        """
        close_threshold = min(connection_model.parent.meta['gui']['editor']['height'],
                              connection_model.parent.meta['gui']['editor']['width)']) / 70.
        # Check distance between all waypoints of the connection to the given coordinates
        for waypoint in connection_model.meta['gui']['editor']['waypoints']:
            if waypoint[0] is not None and waypoint[1] is not None:
                if dist(waypoint, coords) < close_threshold:
                    connection_model.meta['gui']['editor']['waypoints'].remove(waypoint)
                    logger.debug('Connection waypoint removed')
                    self._redraw(True)
                    return True
        return False

    def _add_waypoint(self, connection_model, coords):
        """Adds a waypoint to the given connection

        The methods adds a waypoint at the given coordinates to the given connection (transition or data flow). If
        the connection also has waypoints, it puts the new one between the correct existing ones.
        :param connection_model: The model of the connection to add a waypoint to
        :param coords: The coordinates of the new waypoint
        """

        # The waypoints should exist as dictionary. If not (for any reason), we have to convert it to one
        if isinstance(connection_model.meta['gui']['editor']['waypoints'], dict):
            logger.warn("Connection waypoints was of type dict, expected list")
            connection_model.meta['gui']['editor']['waypoints'] = connection_model.meta['waypoints'].items()

        # Create a list of all connection points, consisting of start, waypoints and end
        points = [(connection_model.meta['gui']['editor']['from_pos_x'],
                   connection_model.meta['gui']['editor']['from_pos_y'])]
        points.extend(connection_model.meta['gui']['editor']['waypoints'])
        points.append((connection_model.meta['gui']['editor']['to_pos_x'],
                       connection_model.meta['gui']['editor']['to_pos_y']))

        # Insert the waypoint at the correct position
        for i in range(len(points) - 1):
            if point_on_line(coords, points[i], points[i + 1]):
                connection_model.meta['gui']['editor']['waypoints'].insert(i, (coords[0], coords[1]))
        logger.debug('Connection waypoint added at {0:.1f} - {1:.1f}'.format(coords[0], coords[1]))
        self._redraw(True)

    def _create_new_transition(self, mouse_position):
        """Tries to create a new transition

        The user can create new transition using drag and drop in the graphical editor. When the mouse is released at
        position, this method extracts the outcome or state beneath that position. Using the stored outcome,
        from which the drag action started, the transition is created.
        :param mouse_position: The mouse position when dropping
        """
        release_selection = self._find_selection(mouse_position[0], mouse_position[1], only_states=True)
        position = self.view.editor.screen_to_opengl_coordinates(mouse_position)
        if isinstance(release_selection, StateModel) and release_selection != self.selection:
            target_state_id = None
            target_outcome = None
            if release_selection == self.selection.parent:
                # Check whether the mouse was released on an outcome
                outcomes_close_threshold = self.selection.parent.meta['gui']['editor']['outcome_radius']
                outcomes = self.selection.parent.meta['gui']['editor']['outcome_pos']
                for key in outcomes:
                    if dist(outcomes[key], position) < outcomes_close_threshold:
                        # This is a possible connection:
                        # The outcome of a state is connected to an outcome of its parent state
                        target_outcome = key

            elif release_selection.parent == self.selection.parent:
                # This is a possible connection:
                # The outcome of a state is connected to another state, which is on the same hierarchy
                target_state_id = release_selection.state.state_id

            if target_state_id is not None or target_outcome is not None:
                state_id = self.selection.state.state_id
                outcome_id = self.selected_outcome[1]
                try:
                    self.selection.parent.state.add_transition(state_id, outcome_id,
                                                               target_state_id, target_outcome)
                except AttributeError as e:
                    logger.debug("Transition couldn't be added: {0}".format(e))
                except Exception as e:
                    logger.error("Unexpected exception while creating transition: {0}".format(e))
        self.selected_outcome = None
        self._redraw(True)

    def _create_new_data_flow(self, mouse_position):
        """Tries to create a new data flow

        The user can create new data flow using drag and drop in the graphical editor. When the mouse is released at
        position, this method extracts the port beneath that position. Using the stored port, from which the drag
        action started, the data flow is created.
        :param mouse_position: The mouse position when dropping
        """
        release_selection = self._find_selection(mouse_position[0], mouse_position[0], only_states=True)
        position = self.view.editor.screen_to_opengl_coordinates(mouse_position)
        if isinstance(release_selection, StateModel):
            target_port = None
            # Data flows are allowed between parent/child, child/parent, between siblings and even within the
            # same state (input to scope, scope to output)
            if release_selection == self.selection.parent or \
                            release_selection.parent == self.selection or \
                            release_selection.parent == self.selection.parent or \
                            release_selection != self.selection:
                # Check whether the mouse was released on an outcome
                connectors_close_threshold = release_selection.meta['gui']['editor']['port_radius']
                connectors = dict(release_selection.meta['gui']['editor']['input_pos'].items() +
                                  release_selection.meta['gui']['editor']['output_pos'].items() +
                                  release_selection.meta['gui']['editor']['scoped_pos'].items())
                for key in connectors:
                    distance = dist((connectors[key][0], connectors[key][1]), (position[0], position[1]))
                    if distance < connectors_close_threshold:
                        # This is a possible connection:
                        target_port = key

            if target_port is not None:
                from_state_id = self.selection.state.state_id
                from_port = self.selected_port[1]
                target_state_id = release_selection.state.state_id

                responsible_parent = self.selection.parent
                if release_selection.parent == self.selection or release_selection == self.selection:
                    responsible_parent = self.selection

                try:
                    responsible_parent.state.add_data_flow(from_state_id, from_port,
                                                           target_state_id, target_port)
                except AttributeError as e:
                    logger.debug("Data flow couldn't be added: {0}".format(e))
                except Exception as e:
                    logger.error("Unexpected exception while creating data flow: {0}".format(e))
        self.selected_port = None
        self._redraw(True)

    def _move_state(self, state_m, new_pos_x, new_pos_y):
        """Move the state to the given position

        The method moves the state and all its child states with their transitions, data flows and waypoints. The
        state is kept within its parent, thus restricting the movement.
        :param awesome_tool.mvc.models.StateModel state_m: The model of the state to be moved
        :param new_pos_x: The desired new x coordinate
        :param new_pos_y: The desired new y coordinate
        """
        old_pos_x = state_m.meta['gui']['editor']['pos_x']
        old_pos_y = state_m.meta['gui']['editor']['pos_y']

        cur_width = state_m.meta['gui']['editor']['width']
        cur_height = state_m.meta['gui']['editor']['height']

        # Keep the state within its container state
        new_pos_x, new_pos_y = self._limit_position_to_state(state_m.parent, new_pos_x, new_pos_y,
                                                             cur_width, cur_height)

        state_m.meta['gui']['editor']['pos_x'] = new_pos_x
        state_m.meta['gui']['editor']['pos_y'] = new_pos_y

        def move_child_states(state, move_x, move_y):
            # Move waypoints
            if isinstance(state, ContainerStateModel):
                for transition in state.transitions:
                    for i, waypoint in enumerate(transition.meta['gui']['editor']['waypoints']):
                        new_pos = (waypoint[0] + move_x, waypoint[1] + move_y)
                        transition.meta['gui']['editor']['waypoints'][i] = new_pos
                for data_flow in state.data_flows:
                    for i, waypoint in enumerate(data_flow.meta['gui']['editor']['waypoints']):
                        new_pos = (waypoint[0] + move_x, waypoint[1] + move_y)
                        data_flow.meta['gui']['editor']['waypoints'][i] = new_pos
                for port_m in state.input_data_ports:
                    old_pos = port_m.meta['gui']['editor']['inner_pos']
                    port_m.meta['gui']['editor']['inner_pos'] = (old_pos[0] + move_x, old_pos[1] + move_y)
                for port_m in state.output_data_ports:
                    old_pos = port_m.meta['gui']['editor']['inner_pos']
                    port_m.meta['gui']['editor']['inner_pos'] = (old_pos[0] + move_x, old_pos[1] + move_y)
            # Move child states
            for child_state in state.states.itervalues():
                child_state.meta['gui']['editor']['pos_x'] += move_x
                child_state.meta['gui']['editor']['pos_y'] += move_y

                if isinstance(child_state, ContainerStateModel):
                    move_child_states(child_state, move_x, move_y)

        # Move all child states in accordance with the state, to keep their relative position
        if isinstance(state_m, ContainerStateModel):
            diff_x = new_pos_x - old_pos_x
            diff_y = new_pos_y - old_pos_y
            move_child_states(state_m, diff_x, diff_y)

        self._redraw()

    def _move_data_port(self, port_m, coords):
        port_info = port_m.meta['gui']['editor']
        if self.drag_origin_offset is None:
            self.drag_origin_offset = (coords[0] - port_info['inner_pos'][0], coords[1] - port_info['inner_pos'][1])

        new_pos = (coords[0] - self.drag_origin_offset[0], coords[1] - self.drag_origin_offset[1])
        if port_m in port_m.parent.output_data_ports:
            new_pos = self._limit_position_to_state(port_m.parent, new_pos[0] - port_info['width'], new_pos[1],
                                                    port_info['width'], port_info['height'])
            new_pos = (new_pos[0] + port_info['width'], new_pos[1])
        else:
            new_pos = self._limit_position_to_state(port_m.parent, new_pos[0], new_pos[1],
                                                    port_info['width'], port_info['height'])
        port_info['inner_pos'] = new_pos
        self._redraw()

    def _resize_state(self, state_m, mouse_resize_coords, d_width, d_height, modifier_keys):
        """Resize the state by the given delta width and height

        The resize function checks the child states and keeps the state around the children, thus limiting the minimum
        size. Two modifier keys can be used to alter the resize options:
         - Ctrl also causes the child states to be resized
         - Shift caused the resized states to keep their width to height ratio
        :param mouse_resize_coords: The coordinates of the mouse
        :param d_width: The desired change in width
        :param d_height: The desired change in height
        :param modifier_keys: The current pressed modifier keys (mask)
        """
        state_editor_data = state_m.meta['gui']['editor']
        # Keep size ratio?
        if int(modifier_keys & SHIFT_MASK) > 0:
            state_size_ratio = state_editor_data['width'] / state_editor_data['height']
            if d_width / state_size_ratio < d_height:
                mouse_resize_coords = (mouse_resize_coords[0],
                                       self.mouse_move_start_coords[1] - d_width / state_size_ratio)
            else:
                mouse_resize_coords = (self.mouse_move_start_coords[0] - d_height * state_size_ratio,
                                       mouse_resize_coords[1])

        width = mouse_resize_coords[0] - state_editor_data['pos_x']
        height_diff = state_editor_data['pos_y'] - mouse_resize_coords[1]
        height = state_editor_data['height'] + height_diff
        min_right_edge = state_editor_data['pos_x']
        max_bottom_edge = state_editor_data['pos_y'] + state_editor_data['height']

        # Resize content?
        if int(modifier_keys & CONTROL_MASK) == 0 and isinstance(self.selection, ContainerStateModel):
            # Check lower right corner of all child states
            for child_state_m in state_m.states.itervalues():
                child_right_edge = child_state_m.meta['gui']['editor']['pos_x'] + \
                                   child_state_m.meta['gui']['editor']['width']
                child_bottom_edge = child_state_m.meta['gui']['editor']['pos_y']
                if min_right_edge < child_right_edge:
                    min_right_edge = child_right_edge
                if max_bottom_edge > child_bottom_edge:
                    max_bottom_edge = child_bottom_edge

        # Check for parent size limitation
        max_right_edge = sys.maxint
        min_bottom_edge = -sys.maxint - 1
        if state_m.parent is not None:
            max_right_edge = state_m.parent.meta['gui']['editor']['pos_x'] + \
                             state_m.parent.meta['gui']['editor']['width']
            min_bottom_edge = state_m.parent.meta['gui']['editor']['pos_y']

        # Desired new edges
        desired_right_edge = state_editor_data['pos_x'] + width
        desired_bottom_edge = state_editor_data['pos_y'] - height_diff

        # Old values
        old_width = state_editor_data['width']
        old_height = state_editor_data['height']
        old_pos_x = state_editor_data['pos_x']
        old_pos_y = state_editor_data['pos_y']

        # Check for all restrictions
        if width > 0:  # Minimum width
            if desired_right_edge > max_right_edge:  # Keep state in its parent
                state_editor_data['width'] = max_right_edge - state_editor_data['pos_x']
            elif desired_right_edge < min_right_edge:  # Surround all children
                state_editor_data['width'] = min_right_edge - state_editor_data['pos_x']
            else:
                state_editor_data['width'] = width
        if height > 0:  # Minimum height
            if desired_bottom_edge > max_bottom_edge:  # Keep state in its parent
                state_editor_data['height'] += state_editor_data['pos_y'] - max_bottom_edge
                state_editor_data['pos_y'] = max_bottom_edge
            elif desired_bottom_edge < min_bottom_edge:  # Surround all children
                state_editor_data['height'] += state_editor_data['pos_y'] - min_bottom_edge
                state_editor_data['pos_y'] = min_bottom_edge
            else:
                state_editor_data['height'] = height
                state_editor_data['pos_y'] -= height_diff

        # Resize factor for width and height
        width_factor = state_editor_data['width'] / old_width
        height_factor = state_editor_data['height'] / old_height

        # Resize content if the state was resized and the modifier key is pressed
        if (width_factor != 1 or height_factor != 1) and int(modifier_keys & CONTROL_MASK) > 0:

            # Recursive call
            def resize_children(state_m, width_factor, height_factor, old_pos_x, old_pos_y):

                def calc_new_pos(old_parent_pos, new_parent_pos, old_self_pos, factor):
                    """Calculate new position of an object

                    The new position is based on the old a new position of the parent, the stretch factor and the old
                    position of the object
                    :param old_parent_pos: Old position (x or y) of the parent
                    :param new_parent_pos: New position (x or y) of the parent
                    :param old_self_pos: Old position (x or y) of the object
                    :param factor: Resize factor of x or y
                    :return: New position of the object (x or y)
                    """
                    diff_pos = old_self_pos - old_parent_pos
                    diff_pos *= factor
                    return new_parent_pos + diff_pos

                # Only container states have content
                if isinstance(state_m, ContainerStateModel):
                    # Resize all transitions
                    for transition_m in state_m.transitions:
                        # By repositioning all waypoints
                        for i, waypoint in enumerate(transition_m.meta['gui']['editor']['waypoints']):
                            new_pos_x = calc_new_pos(old_pos_x, state_m.meta['gui']['editor']['pos_x'],
                                                     waypoint[0], width_factor)
                            new_pos_y = calc_new_pos(old_pos_y, state_m.meta['gui']['editor']['pos_y'],
                                                     waypoint[1], height_factor)
                            transition_m.meta['gui']['editor']['waypoints'][i] = (new_pos_x, new_pos_y)
                    # Resize all data flows
                    for data_flow_m in state_m.data_flows:
                        # By repositioning all waypoints
                        for i, waypoint in enumerate(data_flow_m.meta['gui']['editor']['waypoints']):
                            new_pos_x = calc_new_pos(old_pos_x, state_m.meta['gui']['editor']['pos_x'],
                                                     waypoint[0], width_factor)
                            new_pos_y = calc_new_pos(old_pos_y, state_m.meta['gui']['editor']['pos_y'],
                                                     waypoint[1], height_factor)
                            data_flow_m.meta['gui']['editor']['waypoints'][i] = (new_pos_x, new_pos_y)

                    # Resize all child states
                    for child_state_m in state_m.states.itervalues():
                        child_state_m.meta['gui']['editor']['width'] *= width_factor
                        child_state_m.meta['gui']['editor']['height'] *= height_factor

                        child_old_pos_x = child_state_m.meta['gui']['editor']['pos_x']
                        new_pos_x = calc_new_pos(old_pos_x, state_m.meta['gui']['editor']['pos_x'],
                                                 child_state_m.meta['gui']['editor']['pos_x'], width_factor)
                        child_state_m.meta['gui']['editor']['pos_x'] = new_pos_x

                        child_old_pos_y = child_state_m.meta['gui']['editor']['pos_y']
                        new_pos_y = calc_new_pos(old_pos_y, state_m.meta['gui']['editor']['pos_y'],
                                                 child_state_m.meta['gui']['editor']['pos_y'], height_factor)
                        child_state_m.meta['gui']['editor']['pos_y'] = new_pos_y

                        if isinstance(child_state_m, ContainerStateModel):
                            resize_children(child_state_m, width_factor, height_factor,
                                            child_old_pos_x, child_old_pos_y)

            # Start recursive call of the content resize
            resize_children(state_m, width_factor, height_factor, old_pos_x, old_pos_y)
        self._redraw()

    def _move_view(self, rel_x_motion, rel_y_motion):
        """Move the view according to the relative coordinates

        The whole view/scene is moved, causing the state machine to move within the viewport.
        :param rel_x_motion: Distance to move in x direction
        :param rel_y_motion: Distance to move in y direction
        """
        self.view.editor.left -= rel_x_motion
        self.view.editor.right -= rel_x_motion
        self.view.editor.bottom -= rel_y_motion
        self.view.editor.top -= rel_y_motion
        self._redraw()

    def _handle_zooming(self, pos, direction):
        """Zooms in or out at a given position

        The method zooms increases or decreases the viewport, resulting in a zoom effect. The zoom keeps the current
        position of the cursor within the state machine, allowing to zoom in/out in specific directions.
        :param pos:
        :param direction:
        """
        zoom_in = direction == SCROLL_UP
        zoom_out = direction == SCROLL_DOWN

        if zoom_in or zoom_out:
            old_mouse_pos = self.view.editor.screen_to_opengl_coordinates(pos)

            zoom = 1.25
            zoom = zoom if zoom_in else 1. / zoom

            # Apply centric zoom
            self.view.editor.left *= zoom
            self.view.editor.right *= zoom
            self.view.editor.bottom *= zoom
            self.view.editor.top *= zoom

            # Determine mouse offset to previous position
            aspect = self.view.editor.allocation.width / float(self.view.editor.allocation.height)
            new_mouse_pos = self.view.editor.screen_to_opengl_coordinates(pos)
            diff_x = new_mouse_pos[0] - old_mouse_pos[0]
            diff_y = new_mouse_pos[1] - old_mouse_pos[1]
            if aspect < 1:
                diff_y *= aspect
            else:
                diff_x /= aspect

            # Move view to keep the previous mouse position in the view
            self._move_view(diff_x, diff_y)

    def draw_state(self, state_m, pos_x=0.0, pos_y=0.0, width=100.0, height=100.0, depth=1):
        """Draws a (container) state with all its content

        Mainly contains the logic for drawing (e. g. reading and calculating values). The actual drawing process is
        done in the view, which is called from this method with the appropriate arguments.
        :param state_m: The state to be drawn
        :param pos_x: The default x position if there is no position stored
        :param pos_y: The default y position if there is no position stored
        :param width: The default width if there is no size stored
        :param height: The default height if there is no size stored
        :param depth: The hierarchy level of the state
        """
        assert isinstance(state_m, StateModel)

        # Use default values if no size information is stored
        if not state_m.meta['gui']['editor']['width']:
            state_m.meta['gui']['editor']['width'] = width
        if not state_m.meta['gui']['editor']['height']:
            state_m.meta['gui']['editor']['height'] = height

        width = state_m.meta['gui']['editor']['width']
        height = state_m.meta['gui']['editor']['height']

        # Use default values if no size information is stored
        # Here the possible case of pos_x and posy_y == 0 must be handled
        if not state_m.meta['gui']['editor']['pos_x'] and state_m.meta['gui']['editor']['pos_x'] != 0:
            state_m.meta['gui']['editor']['pos_x'] = pos_x
        if not state_m.meta['gui']['editor']['pos_y'] and state_m.meta['gui']['editor']['pos_y'] != 0:
            state_m.meta['gui']['editor']['pos_y'] = pos_y

        pos_x = state_m.meta['gui']['editor']['pos_x']
        pos_y = state_m.meta['gui']['editor']['pos_y']

        scoped_ports = []
        if isinstance(state_m, ContainerStateModel):
            scoped_ports = state_m.scoped_variables

        # Was the state selected?
        selected_states = self.model.selection.get_states()
        selected = False if state_m not in selected_states else True

        # Is the state active (executing)?
        active = state_m.state.active

        # Call the drawing method of the view
        # The view returns the id of the state in OpenGL and the positions of the outcomes, input and output ports
        (opengl_id, outcome_pos, outcome_radius, port_radius, resize_length) = self.view.editor.draw_state(
            state_m.state.name,
            pos_x, pos_y, width, height,
            state_m.state.outcomes,
            state_m.input_data_ports,
            state_m.output_data_ports,
            scoped_ports,
            selected, active, depth)
        state_m.meta['gui']['editor']['id'] = opengl_id
        state_m.meta['gui']['editor']['outcome_pos'] = outcome_pos
        state_m.meta['gui']['editor']['outcome_radius'] = outcome_radius
        state_m.meta['gui']['editor']['port_radius'] = port_radius
        state_m.meta['gui']['editor']['resize_length'] = resize_length

        if state_m.parent is not None and (
                        state_m.parent.state.start_state == state_m.state.state_id or
                    isinstance(state_m.parent.state, ConcurrencyState)):
            self.draw_start_transition(state_m.parent, state_m, depth)

        # If the state is a container state, we also have to draw its transitions and data flows as well as
        # recursively its child states
        if isinstance(state_m, ContainerStateModel):

            state_ctr = 0
            margin = width / float(25)

            for child_state in state_m.states.itervalues():
                # Calculate default positions for the child states
                # Make the inset from the top left corner
                state_ctr += 1

                child_width = width / 5.
                child_height = height / 5.

                child_pos_x = pos_x + state_ctr * margin
                child_pos_y = pos_y + height - child_height - state_ctr * margin

                self.draw_state(child_state, child_pos_x, child_pos_y, child_width, child_height,
                                depth + 1)

            self.draw_inner_data_ports(state_m, depth)

            self.draw_transitions(state_m, depth)

            self.draw_data_flows(state_m, depth)

        self.handle_new_transition(state_m, depth)

        self.handle_new_data_flow(state_m, depth)

    def draw_inner_data_ports(self, parent_state_m, parent_depth):
        # TODO: move parent_state_m.scoped_variables here?

        parent_info = parent_state_m.meta['gui']['editor']
        port_height = min(parent_info['width'], parent_info['height']) / float(max(25,
                                                                                   len(parent_state_m.input_data_ports),
                                                                                   len(parent_state_m.output_data_ports)
        ))
        max_port_width = min(parent_info['width'], parent_info['height']) / 5.

        num_input_ports = 0
        for port_m in parent_state_m.input_data_ports:
            port = port_m.data_port
            if not isinstance(port_m.meta['gui']['editor']['inner_pos'], tuple):
                pos_x = parent_info['pos_x']
                pos_y = parent_info['pos_y'] + num_input_ports * port_height
                port_m.meta['gui']['editor']['inner_pos'] = (pos_x, pos_y)
            (pos_x, pos_y) = port_m.meta['gui']['editor']['inner_pos']

            selected = port_m in self.model.selection.get_all()
            opengl_id = self.view.editor.draw_inner_input_data_port(port.name, port_m, pos_x, pos_y, max_port_width,
                                                                    port_height, selected, parent_depth + 0.5)
            port_m.meta['gui']['editor']['id'] = opengl_id
            num_input_ports += 1

        num_output_ports = 0
        for port_m in parent_state_m.output_data_ports:
            port = port_m.data_port
            if not isinstance(port_m.meta['gui']['editor']['inner_pos'], tuple):
                pos_x = parent_info['pos_x'] + parent_info['width']
                pos_y = parent_info['pos_y'] + num_output_ports * port_height
                port_m.meta['gui']['editor']['inner_pos'] = (pos_x, pos_y)
            (pos_x, pos_y) = port_m.meta['gui']['editor']['inner_pos']

            selected = port_m in self.model.selection.get_all()
            opengl_id = self.view.editor.draw_inner_output_data_port(port.name, port_m, pos_x, pos_y, max_port_width,
                                                                     port_height, selected, parent_depth + 0.5)
            port_m.meta['gui']['editor']['id'] = opengl_id
            num_output_ports += 1

    def draw_transitions(self, parent_state_m, parent_depth):
        """Draws the transitions belonging to a state

        The method takes all transitions from the given state and calculates their start and end point positions.
        Those are passed together with the waypoints to the view of the graphical editor.
        :param parent_state_m: The model of the container state
        :param parent_depth: The depth of the container state
        """
        for transition_m in parent_state_m.transitions:
            # Get id and references to the from and to state
            from_state_id = transition_m.transition.from_state
            to_state_id = transition_m.transition.to_state
            from_state = parent_state_m.states[from_state_id]
            to_state = None if to_state_id is None else parent_state_m.states[to_state_id]

            assert isinstance(from_state, StateModel), "Transition from unknown state with ID {id:s}".format(
                id=from_state_id)

            try:
                # Set the from coordinates to the outcome coordinates received earlier
                from_x = parent_state_m.states[from_state_id].meta['gui']['editor']['outcome_pos'][
                    transition_m.transition.from_outcome][0]
                from_y = parent_state_m.states[from_state_id].meta['gui']['editor']['outcome_pos'][
                    transition_m.transition.from_outcome][1]
            except Exception as e:
                logger.error("""Outcome position was not found. \
                            maybe the outcome for the transition was not found: {err}""".format(err=e))
                continue

            if to_state is None:  # Transition goes back to parent
                # Set the to coordinates to the outcome coordinates received earlier
                to_x = parent_state_m.meta['gui']['editor']['outcome_pos'][transition_m.transition.to_outcome][0]
                to_y = parent_state_m.meta['gui']['editor']['outcome_pos'][transition_m.transition.to_outcome][1]
            else:
                # Set the to coordinates to the center of the next state
                to_x = to_state.meta['gui']['editor']['pos_x']
                to_y = to_state.meta['gui']['editor']['pos_y'] + to_state.meta['gui']['editor']['height'] / 2

            waypoints = []
            for waypoint in transition_m.meta['gui']['editor']['waypoints']:
                waypoints.append((waypoint[0], waypoint[1]))

            # Let the view draw the transition and store the returned OpenGl object id
            selected = False
            if transition_m in self.model.selection.get_transitions():
                selected = True
            line_width = min(parent_state_m.meta['gui']['editor']['width'],
                             parent_state_m.meta['gui']['editor']['height']) / 25.0
            opengl_id = self.view.editor.draw_transition(from_x, from_y, to_x, to_y, line_width, waypoints,
                                                         selected, parent_depth + 0.5)
            transition_m.meta['gui']['editor']['id'] = opengl_id
            transition_m.meta['gui']['editor']['from_pos_x'] = from_x
            transition_m.meta['gui']['editor']['from_pos_y'] = from_y
            transition_m.meta['gui']['editor']['to_pos_x'] = to_x
            transition_m.meta['gui']['editor']['to_pos_y'] = to_y

    def draw_start_transition(self, parent_state_m, start_state_m, parent_depth):
        parent_info = parent_state_m.meta['gui']['editor']
        start_info = start_state_m.meta['gui']['editor']
        from_x = parent_info['pos_x']
        from_y = parent_info['pos_y'] + parent_info['height'] / 2.
        to_x = start_info['pos_x']
        to_y = start_info['pos_y'] + start_info['height'] / 2.
        line_width = min(parent_info['width'], parent_info['height']) / 25.0
        self.view.editor.draw_transition(from_x, from_y, to_x, to_y, line_width, [], False, parent_depth + 0.5)

    def draw_data_flows(self, parent_state_m, parent_depth):
        """Draw all data flows contained in the given container state

        The method takes all data flows from the given state and calculates their start and end point positions.
        Those are passed together with the waypoints to the view of the graphical editor.
        :param parent_state_m: The model of the container state
        :param parent_depth: The depth pf the container state
        """
        for data_flow_m in parent_state_m.data_flows:
            # Get id and references to the from and to state
            from_state_id = data_flow_m.data_flow.from_state
            to_state_id = data_flow_m.data_flow.to_state
            from_state = parent_state_m if from_state_id == parent_state_m.state.state_id else parent_state_m.states[
                from_state_id]
            to_state = parent_state_m if to_state_id == parent_state_m.state.state_id else parent_state_m.states[
                to_state_id]

            from_key = data_flow_m.data_flow.from_key
            to_key = data_flow_m.data_flow.to_key

            from_port = StateMachineHelper.get_data_port_model(from_state, from_key)
            to_port = StateMachineHelper.get_data_port_model(to_state, to_key)

            if from_port is None:
                logger.warn('Cannot find model of the from data port {0}'.format(from_key))
                continue
            if to_port is None:
                logger.warn('Cannot find model of the to data port {0}'.format(to_key))
                continue

            # For scoped variables, there is no inner and outer connector
            if isinstance(from_port, ScopedVariableModel):
                (from_x, from_y) = from_port.meta['gui']['editor']['connector_pos']
            elif from_state_id == parent_state_m.state.state_id:  # The data flow is connected to the parents input
                (from_x, from_y) = from_port.meta['gui']['editor']['inner_connector_pos']
            else:
                (from_x, from_y) = from_port.meta['gui']['editor']['outer_connector_pos']
            if isinstance(to_port, ScopedVariableModel):
                (to_x, to_y) = to_port.meta['gui']['editor']['connector_pos']
            elif to_state_id == parent_state_m.state.state_id:  # The data flow is connected to the parents output
                (to_x, to_y) = to_port.meta['gui']['editor']['inner_connector_pos']
            else:
                (to_x, to_y) = to_port.meta['gui']['editor']['outer_connector_pos']

            waypoints = []
            for waypoint in data_flow_m.meta['gui']['editor']['waypoints']:
                waypoints.append((waypoint[0], waypoint[1]))

            selected = False
            if data_flow_m in self.model.selection.get_data_flows():
                selected = True
            line_width = min(parent_state_m.meta['gui']['editor']['width'],
                             parent_state_m.meta['gui']['editor']['height']) / 25.0
            opengl_id = self.view.editor.draw_data_flow(from_x, from_y, to_x, to_y, line_width, waypoints,
                                                        selected, parent_depth + 0.5)
            data_flow_m.meta['gui']['editor']['id'] = opengl_id
            data_flow_m.meta['gui']['editor']['from_pos_x'] = from_x
            data_flow_m.meta['gui']['editor']['from_pos_y'] = from_y
            data_flow_m.meta['gui']['editor']['to_pos_x'] = to_x
            data_flow_m.meta['gui']['editor']['to_pos_y'] = to_y

    def handle_new_transition(self, parent_state_m, parent_depth):
        """Responsible for drawing new transition the user creates

        With drag and drop on outcomes, the user can draw new transitions. Here the transition is temporary drawn in
        the graphical editor.
        :param parent_state_m: Model of the container state
        :param parent_depth: Depth of the container state
        """
        if self.selected_outcome is not None and self.last_button_pressed == 1:
            # self.selected_outcome[0] references he list of outcome positions of the outcome state
            if self.selected_outcome[0] == parent_state_m.meta['gui']['editor']['outcome_pos']:
                outcome = self.selected_outcome[0][self.selected_outcome[1]]
                cur = self.mouse_move_last_pos
                line_width = min(parent_state_m.parent.meta['gui']['editor']['width'],
                                 parent_state_m.parent.meta['gui']['editor'][
                                     'height']) / 25.0
                self.view.editor.draw_transition(outcome[0], outcome[1], cur[0], cur[1], line_width, [], True,
                                                 parent_depth + 0.6)

    def handle_new_data_flow(self, parent_state_m, parent_depth):
        """Responsible for drawing new data flows the user creates

        With drag and drop on ports, the user can draw new data flows. Here the data flow is temporary drawn in the
        graphical editor.
        :param parent_state_m: Model of the container state
        :param parent_depth: Depth of the container state
        """
        if self.selected_port is not None and self.last_button_pressed == 1:
            # self.selected_port[0] references the state model pd the port
            if self.selected_port[0] == parent_state_m:
                # Collect positions of all ports
                connectors = dict(parent_state_m.meta['gui']['editor']['input_pos'].items() +
                                  parent_state_m.meta['gui']['editor']['output_pos'].items() +
                                  parent_state_m.meta['gui']['editor']['scoped_pos'].items())
                # self.selected_port[1] stores the key of the port
                connector = connectors[self.selected_port[1]]
                cur = self.mouse_move_last_pos
                ref_state = parent_state_m if not parent_state_m.parent else parent_state_m.parent
                line_width = min(ref_state.meta['gui']['editor']['width'],
                                 ref_state.meta['gui']['editor']['height']) / 25.0
                self.view.editor.draw_data_flow(connector[0], connector[1], cur[0], cur[1], line_width, [], True,
                                                parent_depth + 0.6)

    def _find_selection(self, pos_x, pos_y, only_states=False):
        """Returns the model at the given position

        This method is used when the model (state/transition/data flow) the user clicked on is to be found. The
        position is told to OpenGl and the whole scene is redrawn. From the stack ob objects beneath the position,
        the uppermost one is returned.
        :param pos_x: The x coordinate of the position
        :param pos_y: The y coordinate of the position
        :param only_states: Flag to only search for state models
        :return: The uppermost model beneath the given position, None if nothing was found
        """
        # e.g. sets render mode to GL_SELECT
        self.view.editor.prepare_selection(pos_x, pos_y)
        # draw again
        self.view.editor.expose_init()
        self.draw_state(self.root_state_m)
        self.view.editor.expose_finish()
        # get result
        hits = self.view.editor.find_selection()

        # extract ids
        selection = None

        def get_id(hit):
            if len(hit[2]) > 1:
                return hit[2][1]
            return None

        try:
            selected_ids = map(get_id, hits)  # Get the OpenGL ids for the hits
            selected_ids = filter(lambda opengl_id: opengl_id is not None, selected_ids)  # Filter out Nones
            (selection, selection_depth) = self._selection_ids_to_model(selected_ids, self.root_state_m, 1, None, 0,
                                                                        only_states)
        except Exception as e:
            logger.error("Error while finding selection: {err:s}".format(err=e))
            pass
        return selection

    def _selection_ids_to_model(self, ids, search_state, search_state_depth, selection, selection_depth, only_states):
        """Searches recursively for objects with the given ids

        The method searches recursively and compares all stored ids with the given ones. It finally returns the
        object with the biggest depth (furthest nested)
        :param ids: The ids to search for
        :param search_state: The state to search in
        :param search_state_depth: The depth the search state is in
        :param selection: The currently found object
        :param selection_depth: The depth of the currently found object
        :return: The selected object and its depth
        """
        # Only the element which is furthest down in the hierarchy is selected
        if search_state_depth > selection_depth:
            # Check whether the id of the current state matches an id in the selected ids
            if search_state.meta['gui']['editor']['id'] and search_state.meta['gui']['editor']['id'] in ids:
                # print "possible selection", search_state
                # if so, add the state to the list of selected states
                selection = search_state
                selection_depth = search_state_depth
                # remove the id from the list to fasten up further searches
                ids.remove(search_state.meta['gui']['editor']['id'])

        # Return if there is nothing more to find
        if len(ids) == 0:
            return selection, selection_depth

        # If it is a container state, check its transitions, data flows and child states
        if isinstance(search_state, ContainerStateModel):

            for state in search_state.states.itervalues():
                (selection, selection_depth) = self._selection_ids_to_model(ids, state, search_state_depth + 1,
                                                                            selection, selection_depth, only_states)

            if len(ids) == 0 or search_state_depth < selection_depth or only_states:
                return selection, selection_depth

            def search_selection_in_model_list(model_list, current_selection):
                for model in model_list:
                    if model.meta['gui']['editor']['id'] and model.meta['gui']['editor']['id'] in ids:
                        ids.remove(model.meta['gui']['editor']['id'])
                        current_selection = model
                return current_selection

            selection = search_selection_in_model_list(search_state.input_data_ports, selection)
            selection = search_selection_in_model_list(search_state.output_data_ports, selection)

            if len(ids) == 0:
                return selection, selection_depth

            selection = search_selection_in_model_list(search_state.transitions, selection)

            if len(ids) == 0:
                return selection, selection_depth

            selection = search_selection_in_model_list(search_state.data_flows, selection)

        return selection, selection_depth

    def _delete_selection(self, *args):
        StateMachineHelper.delete_models(self.model.selection.get_all())

    def _add_execution_state(self, *args):
        selection = self.model.selection.get_all()
        if len(selection) > 0:
            model = selection[0]

            if isinstance(model, StateModel):
                StateMachineHelper.add_state(model, StateType.EXECUTION)
            if isinstance(model, TransitionModel) or isinstance(model, DataFlowModel):
                StateMachineHelper.add_state(model.parent, StateType.EXECUTION)
