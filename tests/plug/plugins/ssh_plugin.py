from pwn import process
import logging
import pluggy

logger = logging.getLogger(__name__)
hookimpl = pluggy.HookimplMarker("network_mgr")

class SSHPlugin:
    @hookimpl
    def connect(self, protocol, ip, user, passwd):
        if protocol != "ssh":
            return None
        try:
            sshcmd = f'sshpass -p "{passwd}" ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no {user}@{ip}'
            connection = process(["sh", "-c", sshcmd])
            logger.info(f"SSH Connect {ip} Success")
            return connection
        except Exception as err:
            logger.exception(f"SSH Connect {ip} Fail")
            return None

    @hookimpl
    def disconnect(self, protocol, connection):
        if protocol != "ssh":
            return
        if connection is None:
            logger.error("SSH Context Invalid")
            return
        if connection.connected():
            connection.close()
            logger.info("SSH Disconnect Success")

    @hookimpl
    def execute_command(self, protocol, connection, command):
        if protocol != "ssh":
            return None
        if connection is None:
            logger.error("SSH Context Invalid")
            return None
        if not connection.connected():
            logger.error("SSH Not Connected. Please Reconnect.")
            return None
        try:
            cmd_result = connection.system(command).recvall().decode('utf-8')
            logger.info(f"SSH Execute Command {command} Success. Result:\n{cmd_result}")
            return cmd_result
        except Exception as err:
            logger.exception(f"SSH Execute Command {command} Fail")
            return None

def register_plugin(pm):
    pm.register(SSHPlugin())
