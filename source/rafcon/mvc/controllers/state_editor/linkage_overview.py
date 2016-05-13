"""
.. module:: linkage_overview
   :platform: Unix, Windows
   :synopsis: A module that holds the controller giving footage to the linkage overview.

.. moduleauthor:: Rico Belder


"""

from gtkmvc import Model

from rafcon.mvc.controllers.utils.extended_controller import ExtendedController
from rafcon.mvc.controllers.state_editor.io_data_port_list import DataPortListController
from rafcon.mvc.controllers.state_editor.scoped_variable_list import ScopedVariableListController
from rafcon.mvc.controllers.state_editor.outcomes import StateOutcomesEditorController


class LinkageOverviewController(ExtendedController, Model):
    def __init__(self, model, view):
        ExtendedController.__init__(self, model, view)

        self.add_controller('inputs_ctrl', DataPortListController(model, view['inputs_view'], "input"))
        self.add_controller('output_ctlr', DataPortListController(model, view['outputs_view'], "output"))
        self.add_controller('scoped_ctrl', ScopedVariableListController(model, view['scope_view']))
        self.add_controller('outcomes_ctrl', StateOutcomesEditorController(model, view['outcomes_view']))

        view['inputs_view'].show()
        view['outputs_view'].show()
        view['scope_view'].show()
        view['outcomes_view'].show()