import pluggy

hookspec = pluggy.HookspecMarker("network_mgr")

class NetworkSpec:
    @hookspec
    def connect(self, protocol, ip, user, passwd):
        pass

    @hookspec
    def disconnect(self, protocol, connection):
        pass

    @hookspec
    def execute_command(self, protocol, connection, command):
        pass
