# Copyright (C) 2015-2017 DLR
#
# All rights reserved. This program and the accompanying materials are made
# available under the terms of the Eclipse Public License v1.0 which
# accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# Contributors:
# Annika Wollschlaeger <annika.wollschlaeger@dlr.de>
# Franz Steinmetz <franz.steinmetz@dlr.de>
# Mahmoud Akl <mahmoud.akl@dlr.de>
# Rico Belder <rico.belder@dlr.de>
# Sebastian Brunner <sebastian.brunner@dlr.de>
import os

from gtkmvc import ModelMT
from gtkmvc import Observable

from rafcon.core.state_machine_manager import StateMachineManager
from rafcon.core.storage import storage

from rafcon.gui.models.state_machine import StateMachineModel
from rafcon.gui.singleton import global_runtime_config, global_gui_config

from rafcon.utils.vividict import Vividict
from rafcon.utils import log, storage_utils

logger = log.get_logger(__name__)


class StateMachineManagerModel(ModelMT, Observable):
    """This model class manages a StateMachineManager

    The model class is part of the MVC architecture. It holds the data to be shown (in this case a state machine
    manager).
    Additional to the data of the StateMachineManager its model and the models of state machines hold by those
    these model stores and made observable the selected state machine of the view which have not to be the same
    as the active running one.

    :param StateMachineManager state_machine_manager: The state machine manager to be managed
    """

    # TODO static variable in StateMachineManagerModel
    __sm_manager_creation_counter = 0
    state_machine_manager = None
    selected_state_machine_id = None
    state_machines = {}
    state_machine_mark_dirty = 0
    state_machine_un_mark_dirty = 0

    __observables__ = ("state_machine_manager", "selected_state_machine_id", "state_machines",
                       "state_machine_mark_dirty", "state_machine_un_mark_dirty")

    def __init__(self, state_machine_manager, meta=None):
        """Constructor"""
        ModelMT.__init__(self)  # pass columns as separate parameters
        Observable.__init__(self)
        self.register_observer(self)

        assert isinstance(state_machine_manager, StateMachineManager)

        self.state_machine_manager = state_machine_manager
        self.state_machines = {}
        for sm_id, sm in state_machine_manager.state_machines.iteritems():
            self.state_machines[sm_id] = StateMachineModel(sm, self)

        self._selected_state_machine_id = None
        if len(self.state_machines.keys()) > 0:
            self.selected_state_machine_id = self.state_machines.keys()[0]

        if isinstance(meta, Vividict):
            self.meta = meta
        else:
            self.meta = Vividict()

        # check if the sm_manager_model exists several times
        self.__class__.__sm_manager_creation_counter += 1
        if self.__class__.__sm_manager_creation_counter == 2:
            logger.error("Sm_manager_model exists several times!")
            os._exit(0)

    @property
    def core_element(self):
        return self.state_machine_manager

    def delete_state_machine_models(self):
        for sm_id_to_delete in self.state_machines.keys():
            sm_m = self.state_machines[sm_id_to_delete]
            with sm_m.state_machine.modification_lock():
                sm_m.prepare_destruction()
                del self.state_machines[sm_id_to_delete]
                sm_m.destroy()

    @ModelMT.observe("state_machine_manager", after=True)
    def model_changed(self, model, prop_name, info):
        if info["method_name"] == "add_state_machine":
            logger.debug("Add new state machine model ... ")
            for sm_id, sm in self.state_machine_manager.state_machines.iteritems():
                if sm_id not in self.state_machines:
                    logger.debug("Create new state machine model for state machine with id %s", sm.state_machine_id)
                    with sm.modification_lock():
                        self.state_machines[sm_id] = StateMachineModel(sm, self)
                        self.selected_state_machine_id = sm_id
        elif info["method_name"] == "remove_state_machine":
            sm_id_to_delete = None
            for sm_id, sm_m in self.state_machines.iteritems():
                if sm_id not in self.state_machine_manager.state_machines:
                    sm_id_to_delete = sm_id
                    if self.selected_state_machine_id == sm_id:
                        self.selected_state_machine_id = None
                    break

            if sm_id_to_delete is not None:
                logger.debug("Delete state machine model for state machine with id %s", sm_id_to_delete)
                sm_m = self.state_machines[sm_id_to_delete]
                sm_m.prepare_destruction()
                del self.state_machines[sm_id_to_delete]
                sm_m.destroy()
                sm_m.selection.clear()

    def get_state_machine_model(self, state_m):
        """ Get respective state machine model for handed state model

        :param state_m: State model for which the state machine model should be found
        :return: state machine model
        :rtype: rafcon.gui.models.state_machine.StateMachineModel
        """
        return self.state_machines[state_m.state.get_state_machine().state_machine_id]

    def get_selected_state_machine_model(self):
        """ Get selected state machine model

        :return: state machine model
        :rtype: rafcon.gui.models.state_machine.StateMachineModel
        """
        if self.selected_state_machine_id is None:
            return None

        return self.state_machines[self.selected_state_machine_id]

    @property
    def selected_state_machine_id(self):
        """Property for the _selected_state_machine_id field
        :rtype: int
        """
        return self._selected_state_machine_id

    @selected_state_machine_id.setter
    @Observable.observed
    def selected_state_machine_id(self, selected_state_machine_id):
        if selected_state_machine_id is not None:
            if not isinstance(selected_state_machine_id, int):
                raise TypeError("selected_state_machine_id must be of type int")
        self._selected_state_machine_id = selected_state_machine_id

    @staticmethod
    def clean_file_system_paths_from_not_existing_paths(file_system_paths):
        """ Clean list of paths from elements that can not be reached anymore

        If the path is no more valid it is removed from the list of file system paths.

        :param list file_system_paths: list of file system paths to check for existing
        :return:
        """
        elems_to_delete = []
        for path in file_system_paths:
            if not os.path.exists(path):
                elems_to_delete.append(path)
        for path in elems_to_delete:
            file_system_paths.remove(path)

    def update_recently_opened_state_machines(self, state_machine_m):
        """ Update recently opened list with file system path of handed state machine model

        :param rafcon.gui.models.state_machine.StateMachineModel state_machine_m: State machine model to check
        :return:
        """
        sm = state_machine_m.state_machine
        if sm.file_system_path:
            # check if path is in recent path already
            # logger.info("update recent state machine: {}".format(sm.file_system_path))
            recently_opened_state_machines = global_runtime_config.get_config_value('recently_opened_state_machines', [])
            if sm.file_system_path in recently_opened_state_machines:
                del recently_opened_state_machines[recently_opened_state_machines.index(sm.file_system_path)]
            recently_opened_state_machines.insert(0, sm.file_system_path)
            self.clean_file_system_paths_from_not_existing_paths(recently_opened_state_machines)
            global_runtime_config.set_config_value('recently_opened_state_machines', recently_opened_state_machines)

    def extend_recently_opened_by_current_open_state_machines(self):
        """ Update list with all in the state machine manager opened state machines
        """
        for sm_m in self.state_machines.itervalues():
            self.update_recently_opened_state_machines(sm_m)

    @staticmethod
    def prepare_recent_opened_state_machines_list_for_storage():
        """ Reduce number of paths in the recent opened state machines to limit from gui config
        """
        num = global_gui_config.get_config_value('NUMBER_OF_RECENT_OPENED_STATE_MACHINES_STORED')
        state_machine_paths = global_runtime_config.get_config_value('recently_opened_state_machines', [])
        global_runtime_config.set_config_value('recently_opened_state_machines', state_machine_paths[:num])

    @staticmethod
    def reset_session_storage():
        global_runtime_config.set_config_value('open_tabs', [])

    def store_session(self):
        """ Stores reference backup information for all open tabs into runtime config

        The backup of never stored tabs (state machines) and not stored state machine changes will be triggered a last
        time to secure data lose.
        """
        from rafcon.gui.models.auto_backup import AutoBackupModel
        # check if there are dirty state machines -> use backup file structure maybe it is already stored
        for sm_m in self.state_machines.itervalues():
            if hasattr(sm_m, 'auto_backup'):
                if sm_m.state_machine.marked_dirty:
                    sm_m.auto_backup.perform_temp_storage()
            else:
                # generate a backup
                sm_m.auto_backup = AutoBackupModel(sm_m)
        # store final state machine meta data to restore session in the next run
        list_of_tab_meta = [sm_m.auto_backup.meta for sm_m in self.state_machines.itervalues()]
        global_runtime_config.set_config_value('open_tabs', list_of_tab_meta)

    def restore_session_from_storage(self):
        """ Restore stored tabs from runtime config

        The method checks if the last status of a state machine is in the backup or in tis original path and loads it
        from there. The original path of these state machines are also insert into the recently opened state machines
        list.
        """
        # TODO add a dirty lock for a crashed rafcon instance also into restore session feature
        # TODO in case a dialog is needed to give the user control
        # TODO combine this and auto-backup in one structure/controller/observer
        from rafcon.gui.models.auto_backup import recover_state_machine_from_backup
        # check if session storage exists
        open_tabs = global_runtime_config.get_config_value('open_tabs', None)
        if open_tabs is None:
            logger.info("No session recovery from runtime config file")
            return

        # load and recover state machines like they were opened before
        for idx, sm_meta_dict in enumerate(open_tabs):
            from_backup_path = None
            # TODO do this decision before storing or maybe store the last stored time in the auto backup?!
            # pick folder name dependent on time, and backup meta data existence
            # problem is that the backup time is maybe not the best choice
            if 'last_backup' in sm_meta_dict:
                last_backup_time = storage_utils.get_float_time_for_string(sm_meta_dict['last_backup']['time'])
                if 'last_saved' in sm_meta_dict:
                    last_save_time = storage_utils.get_float_time_for_string(sm_meta_dict['last_saved']['time'])
                    backup_marked_dirty = sm_meta_dict['last_backup']['marked_dirty']
                    if last_backup_time > last_save_time and backup_marked_dirty:
                        from_backup_path = sm_meta_dict['last_backup']['file_system_path']
                else:
                    from_backup_path = sm_meta_dict['last_backup']['file_system_path']
            elif 'last_saved' in sm_meta_dict:
                # print "### open last saved", sm_meta_dict['last_saved']['file_system_path']
                pass
            else:
                logger.error("A tab was stored into session storage dictionary {0} without any recovery path"
                             "".format(sm_meta_dict))
                continue

            # check in case that the backup folder is valid or use last saved path
            if from_backup_path is not None and not os.path.isdir(from_backup_path):
                logger.warning("The restore of tab {0} from backup path {1} was not possible. "
                               "The last saved path will be used what maybe include lose of changes."
                               "".format(idx, from_backup_path))
                from_backup_path = None

            # open state machine
            if from_backup_path is not None:
                # open state machine, recover mark dirty flags, cleans dirty lock files
                logger.info("Recover from backup {0}".format(from_backup_path))
                recover_state_machine_from_backup(from_backup_path)
            else:
                if 'last_saved' not in sm_meta_dict or sm_meta_dict['last_saved']['file_system_path'] is None:
                    continue
                path = sm_meta_dict['last_saved']['file_system_path']
                if not os.path.isdir(path):
                    logger.warning("The tab can not be open. The restore of tab {0} from common path {1} was not "
                                   "possible.".format(idx, path))
                    continue
                # logger.info("restore from last saved", path, sm_meta_dict)
                state_machine = storage.load_state_machine_from_path(path)
                self.state_machine_manager.add_state_machine(state_machine)

        self.extend_recently_opened_by_current_open_state_machines()
