from awesome_server.mvc.controller.extended_controller import ExtendedController
from awesome_server.mvc.controller.network_controller import NetworkMode
from awesome_server.mvc.models.connection_manager import ConnectionManagerModel

from awesome_server.utils import constants

# ------------------------JUST FOR DEBUG------------------------todo: remove
from awesome_server.mvc.controller.network_controller_t_client import ClientController
# --------------------------------------------------------------


class DebugViewController(ExtendedController):

    # ------------------------JUST FOR DEBUG------------------------todo: remove
    port = 7777
    # --------------------------------------------------------------

    def __init__(self, model, view):
        assert isinstance(model, ConnectionManagerModel)
        ExtendedController.__init__(self, model, view)

        model.connection_manager.add_tcp_connection(constants.TCP_PORT)
        model.connection_manager.add_udp_connection(constants.UDP_PORT)

        view["send_button"].connect("clicked", self.send_button_clicked)

# ------------------------JUST FOR DEBUG------------------------todo: remove
        view["add_tcp_button"].connect("clicked", self.add_tcp)
        view["add_udp_button"].connect("clicked", self.add_udp)

    def add_tcp(self, widget, event=None):
        ClientController(self.view, 8888, NetworkMode.TCP)
        # print self.server_tcp.get_connections()

    def add_udp(self, widget, event=None):
        ClientController(self.view, self.port, NetworkMode.UDP)
        self.port += 1
# --------------------------------------------------------------

    def send_button_clicked(self, widget, event=None):
        combo = self.view["combobox"]
        tree_iter = combo.get_active_iter()
        if tree_iter is not None:
            model = combo.get_model()
            name, ip, port = model[tree_iter]

            con = self.model.get_udp_connection_for_address((ip, port))
            con.send_message(self.view["entry"].get_text(), (ip, port))

    @ExtendedController.observe("_udp_clients", after=True)
    def add_udp_client(self, model, prop_name, info):
        clients = info.instance[info.args[0]]
        if self.view:
            last_index = len(clients) - 1
            ip, port = clients[last_index]
            self.view["liststore"].append(["%s:%d" % (ip, port), ip, port])
            self.view["combobox"].set_active(last_index)

    @ExtendedController.observe("_tcp_messages_received", after=True)
    def handle_tcp_message_received(self, model, prop_name, info):
        self.print_msg(str(info["args"]))

    @ExtendedController.observe("_udp_messages_received", after=True)
    def handle_udp_message_received(self, mode, prop_name, info):
        self.print_msg(str(info["args"]))

    def print_msg(self, msg):
        buffer = self.view["textview"].get_buffer()
        buffer.insert(buffer.get_end_iter(), msg + "\n")