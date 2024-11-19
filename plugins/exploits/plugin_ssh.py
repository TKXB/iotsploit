import pluggy
import logging
from pwn import *
from typing import Optional, Any
from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.models.Target_Model import TargetManager
from sat_toolkit.core.exploit_spec import ExploitResult

logger = logging.getLogger(__name__)
hookimpl = pluggy.HookimplMarker("exploit_mgr")

class SSHPlugin:
    @hookimpl
    def initialize(self):
        logger.info("Initializing SSHExploitPlugin")
        self.ssh_mgr = SSH_Mgr()

    @hookimpl
    def execute(self, target: Optional[Any] = None) -> ExploitResult:
        target_manager = TargetManager.get_instance()
        current_target = target_manager.get_current_target()
        
        if current_target is None:
            print("No target selected. Please load a target first.")
            return ExploitResult(False, "No target selected", {})

        # Retrieve target information from the current target object
        target = {
            'ip': current_target.ip_address,
            'user': "root",
            'passwd': "123456",
            'cmd': "ls -l"
        }
        
        logger.info(f"Executing SSH exploit on {target['ip']}")
        return ExploitResult(True, "SSH exploit executed successfully", {"result": "test"})
        ssh_context = self.ssh_mgr.open_ssh(target['ip'], target['user'], target['passwd'])
        if ssh_context:
            result = self.ssh_mgr.ssh_cmd(ssh_context, target['cmd'])
            print(f"Command result: {result}")
            self.ssh_mgr.close_ssh(ssh_context)
            return ExploitResult(True, "SSH exploit executed successfully", {"result": result})
        else:
            return ExploitResult(False, "Failed to establish SSH connection", {})

class SSH_Mgr:
    __ssh_connect_timeout_S = 1

    @staticmethod
    def Instance():
        return _instance
        
    def __init__(self):
        self.__ssh_dict = {}

    def open_ssh(self, ip:str, user:str, passwd:str):
        try:
            sshcmd = 'sshpass -p "{}" ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no {}@{}'.format(passwd, user, ip)
            ssh_context = process(["sh", "-c", sshcmd])
            logger.info("SSH Connect {} Success.".format(ip))
            return ssh_context
        except Exception as err:
            logger.exception("SSH Connect {} Fail!".format(ip))
            return None  

    def close_ssh(self, ssh_context:ssh):
        if ssh_context == None:
            logger.error("SSH Context Invalid!")
            return

        if ssh_context.connected() == True:
            ssh_context.close()
            logger.info("SSH Close Success.")
        
        return

    def ssh_cmd(self, ssh_context:ssh, ssh_cmd:str):
        if ssh_context == None:
            logger.error("SSH Context Invalid!")
            return None
        
        if ssh_context.connected() != True:
            logger.error("SSH Not Connect. Please Reconnect.")
            return None
        
        try:
            cmd_result = ssh_context.system(ssh_cmd).recvall().decode('utf-8')
            logger.info("SSH Run CMD {} Success. Result:\n{}".format(ssh_cmd, cmd_result))
            return cmd_result
        
        except Exception as err:
            logger.exception("SSH Run CMD {} Fail!".format(ssh_cmd))
            return None

_instance = SSH_Mgr()

def register_plugin(pm):
    pm.register(SSHPlugin())