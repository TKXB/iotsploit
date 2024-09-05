import telnetlib
import logging
import pluggy

logger = logging.getLogger(__name__)
hookimpl = pluggy.HookimplMarker("network_mgr")

class TelnetPlugin:
    @hookimpl
    def connect(self, protocol, ip, user, passwd):
        if protocol != "telnet":
            return None
        try:
            connection = telnetlib.Telnet(ip)
            connection.read_until(b"login: ")
            connection.write(user.encode('ascii') + b"\n")
            connection.read_until(b"Password: ")
            connection.write(passwd.encode('ascii') + b"\n")
            logger.info(f"Telnet Connect {ip} Success")
            return connection
        except Exception as err:
            logger.exception(f"Telnet Connect {ip} Fail")
            return None

    @hookimpl
    def disconnect(self, protocol, connection):
        if protocol != "telnet":
            return
        if connection:
            connection.close()
            logger.info("Telnet Disconnect Success")

    @hookimpl
    def execute_command(self, protocol, connection, command):
        if protocol != "telnet":
            return None
        if connection is None:
            logger.error("Telnet Context Invalid")
            return None
        try:
            connection.write(command.encode('ascii') + b"\n")
            cmd_result = connection.read_all().decode('ascii')
            logger.info(f"Telnet Execute Command {command} Success. Result:\n{cmd_result}")
            return cmd_result
        except Exception as err:
            logger.exception(f"Telnet Execute Command {command} Fail")
            return None

def register_plugin(pm):
    pm.register(TelnetPlugin())
