import ftplib
import logging
import pluggy

logger = logging.getLogger(__name__)
hookimpl = pluggy.HookimplMarker("network_mgr")

class FTPPlugin:
    @hookimpl
    def connect(self, protocol, ip, user, passwd):
        if protocol != "ftp":
            return None
        try:
            connection = ftplib.FTP(ip)
            connection.login(user=user, passwd=passwd)
            logger.info(f"FTP Connect {ip} Success")
            return connection
        except Exception as err:
            logger.exception(f"FTP Connect {ip} Fail")
            return None

    @hookimpl
    def disconnect(self, protocol, connection):
        if protocol != "ftp":
            return
        if connection:
            connection.quit()
            logger.info("FTP Disconnect Success")

    @hookimpl
    def execute_command(self, protocol, connection, command):
        if protocol != "ftp":
            return None
        if connection is None:
            logger.error("FTP Context Invalid")
            return None
        try:
            cmd_result = connection.voidcmd(command)
            logger.info(f"FTP Execute Command {command} Success. Result:\n{cmd_result}")
            return cmd_result
        except Exception as err:
            logger.exception(f"FTP Execute Command {command} Fail")
            return None

def register_plugin(pm):
    pm.register(FTPPlugin())
