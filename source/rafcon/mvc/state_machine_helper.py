from rafcon.utils import log
from rafcon.statemachine.enums import UNIQUE_DECIDER_STATE_ID

logger = log.get_logger(__name__)

from rafcon.statemachine.states.state import State
from rafcon.statemachine.states.container_state import ContainerState
from rafcon.statemachine.states.library_state import LibraryState
from rafcon.statemachine.states.execution_state import ExecutionState
from rafcon.statemachine.states.hierarchy_state import HierarchyState
from rafcon.statemachine.states.barrier_concurrency_state import BarrierConcurrencyState
from rafcon.statemachine.states.preemptive_concurrency_state import PreemptiveConcurrencyState
from rafcon.statemachine.enums import StateType
from rafcon.mvc.models import StateModel, AbstractStateModel, ContainerStateModel, TransitionModel, DataFlowModel
from rafcon.mvc.models.data_port import DataPortModel
from rafcon.mvc.models.outcome import OutcomeModel
from rafcon.mvc.models.state_machine import StateMachineModel
from rafcon.mvc.models.scoped_variable import ScopedVariableModel
from rafcon.statemachine.singleton import library_manager
import rafcon.mvc.singleton


def delete_model(model, raise_exceptions=False):
    """Deletes a model of its state machine

    If the model is one of state, data flow or transition, it is tried to delete that model together with its
    data from the corresponding state machine.

    :param model: The model to delete
    :return: True if successful, False else
    """
    container_m = model.parent
    if container_m is None:
        return False
    assert isinstance(container_m, ContainerStateModel)
    if isinstance(model, AbstractStateModel):
        state_id = model.state.state_id
        try:
            if state_id in container_m.state.states:
                container_m.state.remove_state(state_id)
                return True
        except AttributeError as e:
            if not raise_exceptions:
                logger.error("The state with the ID {0} and the name {1} could not be deleted: {2}".format(
                    state_id, model.state.name, e.message))
            else:
                raise

    elif isinstance(model, TransitionModel):
        transition_id = model.transition.transition_id
        try:
            if transition_id in container_m.state.transitions:
                container_m.state.remove_transition(transition_id)
                return True
        except AttributeError as e:
            if not raise_exceptions:
                logger.error("The transition with the ID {0} could not be deleted: {1}".format(
                    transition_id, e.message))
            else:
                raise

    elif isinstance(model, DataFlowModel):
        data_flow_id = model.data_flow.data_flow_id
        try:
            if data_flow_id in container_m.state.data_flows:
                container_m.state.remove_data_flow(data_flow_id)
                return True
        except AttributeError as e:
            if not raise_exceptions:
                logger.error("The data flow with the ID {0} could not be deleted: {1}".format(
                    data_flow_id, e.message))
            else:
                raise

    elif isinstance(model, ScopedVariableModel):
        scoped_variable_id = model.scoped_variable.data_port_id
        try:
            if scoped_variable_id in container_m.state.scoped_variables:
                container_m.state.remove_scoped_variable(scoped_variable_id)
                return True
        except AttributeError as e:
            if not raise_exceptions:
                logger.error("The scoped variable with the ID {0} could not be deleted: {1}".format(
                    scoped_variable_id, e.message))
            else:
                raise

    elif isinstance(model, DataPortModel):
        port_id = model.data_port.data_port_id
        try:
            if port_id in container_m.state.input_data_ports:
                container_m.state.remove_input_data_port(port_id)
                return True
            elif port_id in container_m.state.output_data_ports:
                container_m.state.remove_output_data_port(port_id)
                return True
        except AttributeError as e:
            if not raise_exceptions:
                logger.error("The data port with the ID {0} could not be deleted: {1}".format(
                    port_id, e.message))
            else:
                raise

    return False


def delete_models(models, raise_exceptions=False):
    """Deletes all given models from their state machines

    Calls the :func:`delete_model` for all models given.

    :param models: A single model or a list of models to be deleted
    :return: The number of models that were successfully deleted
    """
    num_deleted = 0
    # If only one model is given, make a list out of it
    if not isinstance(models, list):
        models = [models]
    for model in models:
        if delete_model(model, raise_exceptions):
            num_deleted += 1
    return num_deleted


def delete_selected_elements(state_machine_m):
    if len(state_machine_m.selection.get_all()) > 0:
        delete_models(state_machine_m.selection.get_all())
        state_machine_m.selection.clear()
        return True


def add_state(container_state_m, state_type):
    """Add a state to a container state

    Adds a state of type state_type to the given container_state

    :param rafcon.mvc.models.container_state.ContainerState container_state_m: A model of a container state to add
      the new state to
    :param rafcon.statemachine.enums.StateType state_type: The type of state that should be added
    :return: True if successful, False else
    """
    if container_state_m is None:
        logger.error("Cannot add a state without a parent.")
        return False

    if not isinstance(container_state_m, StateModel) or \
            (isinstance(container_state_m, StateModel) and not isinstance(container_state_m, ContainerStateModel)):
        logger.error("Parent state must be a container, for example a Hierarchy State." + str(container_state_m))
        return False

    new_state = None
    if state_type == StateType.HIERARCHY:
        new_state = HierarchyState()
    elif state_type == StateType.EXECUTION:
        new_state = ExecutionState()
    elif state_type == StateType.BARRIER_CONCURRENCY:
        new_state = BarrierConcurrencyState()
    elif state_type == StateType.PREEMPTION_CONCURRENCY:
        new_state = PreemptiveConcurrencyState()

    if new_state is None:
        logger.error("Cannot create state of type {0}".format(state_type))
        return False

    container_state_m.state.add_state(new_state)
    return True


def add_new_state(state_machine_m, state_type):
    """Triggered when shortcut keys for adding a new state are pressed, or Menu Bar "Edit, Add State" is clicked.

    Adds a new state only if the parent state (selected state) is a container state, and if the graphical editor or
    the state machine tree are in focus.
    """
    assert isinstance(state_machine_m, StateMachineModel)

    if state_type not in list(StateType):
        state_type = StateType.EXECUTION

    selection = state_machine_m.selection.get_all()
    if not selection:
        logger.warn("Please select the desired parent state, before adding a new state")
        return
    model = selection[0]

    if isinstance(model, StateModel):
        return add_state(model, state_type)
    if isinstance(model, (TransitionModel, DataFlowModel)) or \
            isinstance(model, (DataPortModel, OutcomeModel)) and isinstance(model.parent, ContainerStateModel):
        return add_state(model.parent, state_type)


def create_new_state_from_state_with_type(source_state, target_state_class):
    """The function duplicates/transforms a state to a new state type. If the source state type and the new state
    type both are ContainerStates the new state will have not transitions to force the user to explicitly re-order
    the logical flow according the paradigm of the new state type.

    :param source_state: previous/original state that is to transform into a new state type (target_state_class)
    :param target_state_class: the final state class type
    :return:
    """

    current_state_is_container = isinstance(source_state, ContainerState)
    new_state_is_container = issubclass(target_state_class, ContainerState)

    if current_state_is_container and new_state_is_container:  # TRANSFORM from CONTAINER- TO CONTAINER-STATE

        # by default all transitions are left out if the new and original state are container states
        # -> because switch from Barrier, Preemptive or Hierarchy has always different rules
        state_transitions = {}
        state_start_state_id = None
        logger.info("Type change from %s to %s" % (type(source_state).__name__, target_state_class.__name__))

        # decider state is removed because it is unique for BarrierConcurrencyState
        if isinstance(source_state, BarrierConcurrencyState):
            source_state.remove_state(UNIQUE_DECIDER_STATE_ID, force=True)
            assert UNIQUE_DECIDER_STATE_ID not in source_state.states

        new_state = target_state_class(name=source_state.name, state_id=source_state.state_id,
                                       input_data_ports=source_state.input_data_ports,
                                       output_data_ports=source_state.output_data_ports,
                                       outcomes=source_state.outcomes, states=source_state.states,
                                       transitions=state_transitions, data_flows=source_state.data_flows,
                                       start_state_id=state_start_state_id,
                                       scoped_variables=source_state.scoped_variables,
                                       v_checker=source_state.v_checker)
    else:  # TRANSFORM from EXECUTION- TO CONTAINER-STATE or FROM CONTAINER- TO EXECUTION-STATE
        new_state = target_state_class(name=source_state.name, state_id=source_state.state_id,
                                       input_data_ports=source_state.input_data_ports,
                                       output_data_ports=source_state.output_data_ports,
                                       outcomes=source_state.outcomes)

    if source_state.description is not None and len(source_state.description) > 0:
        new_state.description = source_state.description

    return new_state


def extract_child_models_of_of_state(state_m, new_state_class):
    """Retrieve child models of state model

    The function stores model information like meta data of external (in the parent of the state) related
    transitions
    and data flows as well as StateModel-attributes of the original Models (of the original state) for operations
    on the newly generated models after core-operations. Additionally the function cares about selection issues.

    :param state_m: state model of which children are to be extracted from
    :param new_state_class: The type of the new class
    :return:
    """
    # check if root state and which type of state
    assert isinstance(state_m, StateModel)
    assert issubclass(new_state_class, State)
    orig_state = state_m.state  # only here to get the input parameter of the Core-function

    current_state_is_container = isinstance(orig_state, ContainerState)
    new_state_is_container = issubclass(new_state_class, ContainerState)

    # define which model references to hold for new state
    model_properties = ['meta', 'input_data_ports', 'output_data_ports', 'outcomes']
    if current_state_is_container and new_state_is_container:  # hold some additional references
        # transition are removed when changing the state type, thus do not copy them
        model_properties.extend(['states', 'data_flows', 'scoped_variables'])

    child_models = {}
    for prop_name in model_properties:
        child_models[prop_name] = state_m.__getattribute__(prop_name)

    return child_models


def create_state_model_for_state(new_state, state_element_models):
    """Create a new state model with the defined properties

    A state model is created for a state of the type of new_state. All child models in state_element_models (
    model list for port, connections and states) are added to the new model.

    :param new_state: The new state object with the correct type
    :param state_element_models: All state element and child state models of the original state model
    :return: New state model for new_state with all childs of state_element_models
    """
    from rafcon.mvc.models.abstract_state import get_state_model_class_for_state
    state_m_class = get_state_model_class_for_state(new_state)
    new_state_m = state_m_class(new_state)

    # handle special case of BarrierConcurrencyState -> secure decider state model to not be overwritten
    if isinstance(new_state, BarrierConcurrencyState):
        decider_state_m = new_state_m.states[UNIQUE_DECIDER_STATE_ID]

    # by default all transitions are left out if the new and original state are container states
    # -> because Barrier, Preemptive or Hierarchy has always different rules
    if isinstance(state_element_models, ContainerStateModel):
        state_element_models['transitions'] = []

    # insert and link original state model attributes (child-models) into/with new state model (the new parent)
    for prop_name, value in state_element_models.iteritems():
        # look_out: all model properties get overwritten here
        new_state_m.__setattr__(prop_name, value)
        # Set the parent of all child models to the new state model
        if prop_name == "states":
            for state_m in new_state_m.states.itervalues():
                state_m.parent = new_state_m
            # Delete decider state model, if existing
            if UNIQUE_DECIDER_STATE_ID in new_state_m.states:
                del new_state_m.states[UNIQUE_DECIDER_STATE_ID]
        if prop_name in ['outcomes', 'input_data_ports', 'output_data_ports', 'data_flows', 'scoped_variables']:
            for model in new_state_m.__getattribute__(prop_name):
                model.parent = new_state_m

    # handle special case of BarrierConcurrencyState -> re-insert decider state model
    if isinstance(new_state, BarrierConcurrencyState):
        decider_state_m.parent = new_state_m
        new_state_m.states[UNIQUE_DECIDER_STATE_ID] = decider_state_m
    
    return new_state_m


def reduce_to_parent_states(models):
    models_to_remove = []
    for model in models:
        parent_m = model.parent
        while parent_m is not None:
            if parent_m in models:
                models_to_remove.append(model)
                break
            parent_m = parent_m.parent
    for model in models_to_remove:
        models.remove(model)
    return models


def get_root_state_model(state_m, library_root=False):
    """Get the root state for a given state model

    The method walks up the state tree from the given state model to find the root state model (which doesn't
    have a parent state). If the flag library_root is set to True, the root is defined as root of the library and
    not of the whole state machine.

    :param state_m: The state model to start from
    :param library_root: Flag to specify if the root of teh library is searched
    :return: The model of the root state (either of the state machine or the library)
    """
    while not state_m.state.is_root_state and (not library_root or not isinstance(state_m.state, LibraryState)):
        state_m = state_m.parent
    return state_m


def get_state_model_for_state(state):
    """Return the model for a given state

    The function looks up the state machine id for the given state and walks the state tree up until it find the
    model of the given state.

    :param state: The state of which the state model is searched
    :return: The model corresponding to state
    """
    assert isinstance(state, State)
    state_machine_id = state.get_sm_for_state().state_machine_id
    state_machine_m = rafcon.mvc.singleton.state_machine_manager_model.state_machines[state_machine_id]
    state_m = state_machine_m.root_state
    state_path = state.get_path()
    path_item_list = state_path.split('/')
    root_state_id = path_item_list.pop(0)
    assert state_m.state.state_id == root_state_id
    while len(path_item_list) > 0:
        state_id = path_item_list.pop(0)
        if isinstance(state_m.state, LibraryState):
            return state_m  # There are no models for states within library states, yes
        state_m = state_m.states[state_id]
    assert state == state_m.state  # Final check
    return state_m


def get_state_machine_model_for_state(state):
    """Return the state machine model containing the given state

    :param state: The state of which the state machine model is searched
    :return: The state machine model containing the state
    """
    assert isinstance(state, State)
    state_machine_id = state.get_sm_for_state().state_machine_id
    state_machine_m = rafcon.mvc.singleton.state_machine_manager_model.state_machines[state_machine_id]
    return state_machine_m


def insert_state(state, as_template=False):
    """Adds a State to the selected state

    :param state: the state which is inserted
    :param as_template:
    :return: boolean: success of the insertion
    """
    smm_m = rafcon.mvc.singleton.state_machine_manager_model

    if state is None:
        logger.error("Please select a library state")
        return False

    if not smm_m.selected_state_machine_id:
        logger.error("Please select a container state within a state machine first")
        return False

    current_selection = smm_m.state_machines[smm_m.selected_state_machine_id].selection
    if len(current_selection.get_states()) > 1:
        logger.error("Please select exactly one state for the insertion")
        return False

    if len(current_selection.get_states()) == 0:
        logger.error("Please select a state for the insertion")
        return False

    current_state_m = current_selection.get_states()[0]
    current_state = current_state_m.state
    if not isinstance(current_state, ContainerState):
        logger.error("States can only be inserted in container states")
        return False

    if not as_template:
        current_state.add_state(state)
        return True
    # If inserted as template, we have to extract the state_copy and load the meta data manually
    else:
        template = state.state_copy
        orig_state_id = template.state_id
        template.change_state_id()
        current_state.add_state(template)

        # reset the parent of all ports (logical + data ports)
        # as in the setter function the parent is reset it can be used here
        template.input_data_ports = template.input_data_ports
        template.output_data_ports = template.output_data_ports
        template.outcomes = template.outcomes

        # load meta data
        from os.path import join
        lib_os_path, _, _ = library_manager.get_os_path_to_library(state.library_path, state.library_name)
        root_state_path = join(lib_os_path, orig_state_id)
        template_m = current_state_m.states[template.state_id]
        template_m.load_meta_data(root_state_path)
        # Causes the template to be resized
        template_m.temp['gui']['editor']['template'] = True
        return True


def insert_self_transition_meta_data(state_m, t_id, origin='graphical_editor', combined_action=False):

    state_m_meta = state_m.meta['gui']['editor_opengl']
    t_m = state_m.parent.get_transition_m(t_id)
    outcome_id = t_m.transition.from_outcome
    first_point_x = state_m_meta['rel_pos'][0] + 1.3*state_m_meta['size'][0]
    first_point_y = state_m_meta['rel_pos'][1] - 0.1*outcome_id*state_m_meta['size'][1]
    second_point_x = state_m_meta['rel_pos'][0] + 0.5*state_m_meta['size'][0]
    second_point_y = state_m_meta['rel_pos'][1] + (0.5-0.1*outcome_id)*state_m_meta['size'][1]

    t_m.meta['gui']['editor_opengl'].update({'waypoints': [(first_point_x, first_point_y),
                                                           (second_point_x, second_point_y)]})
    from rafcon.mvc.models.signals import MetaSignalMsg
    if combined_action:
        t_m.meta_signal.emit(MetaSignalMsg(origin=origin, change='append_to_last_change'))
    else:
        t_m.meta_signal.emit(MetaSignalMsg(origin=origin, change='viapoint_position'))