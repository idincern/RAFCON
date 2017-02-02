#!/usr/bin/env python

import pytest
from pytest import raises
import testing_utils
import signal

import rafcon
from rafcon.core import interface, start
from rafcon.core.custom_exceptions import LibraryNotFoundException
from rafcon.core.states.library_state import LibraryState
from rafcon.core.storage import storage
import rafcon.core.singleton as sm_singletons
# needed for yaml parsing
from rafcon.core.states.hierarchy_state import HierarchyState
from rafcon.core.states.execution_state import ExecutionState
from rafcon.core.states.preemptive_concurrency_state import PreemptiveConcurrencyState
from rafcon.core.states.barrier_concurrency_state import BarrierConcurrencyState

from rafcon.utils import log
logger = log.get_logger("start-no-gui")
logger.info("initialize RAFCON ... ")


def show_notice(query):
    return ""  # just take note of the missing library


def open_folder(query):
    if "library2_for_relocation_test" in query:
        return None  # the first relocation has to be aborted
    else:
        return testing_utils.get_test_sm_path("unit_test_state_machines/library_relocation_test_source/library1_for_relocation_test_relocated")


def test_library_relocation(caplog):

    testing_utils.initialize_rafcon(libraries={"test_scripts": testing_utils.TEST_ASSETS_PATH})

    interface.open_folder_func = open_folder

    interface.show_notice_func = show_notice

    state_machine = storage.load_state_machine_from_path(testing_utils.get_test_sm_path(
        "unit_test_state_machines/library_relocation_test"))

    rafcon.core.singleton.state_machine_manager.add_state_machine(state_machine)

    rafcon.core.singleton.state_machine_execution_engine.start()
    rafcon.core.singleton.state_machine_execution_engine.join()
    rafcon.core.singleton.state_machine_execution_engine.stop()

    assert state_machine.root_state.output_data["output_0"] == 27

    testing_utils.assert_logger_warnings_and_errors(caplog, 0, 1)
    testing_utils.terminate_rafcon(config=True, gui_config=False)

    logger.info("State machine execution finished!")


def test_library_relocation_exception():
    logger.info("Load not existing library, expect exception to be raised...")
    with raises(LibraryNotFoundException):
        print LibraryState('aasdasd', 'basdasd', allow_user_interaction=False)


if __name__ == '__main__':
    pytest.main([__file__, '-s'])