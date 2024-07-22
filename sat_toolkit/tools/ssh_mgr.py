import logging
logger = logging.getLogger(__name__)

from pwn import *
from sat_toolkit.tools.wifi_mgr import WiFi_Mgr
from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.sat_utils import *


class SSH_Mgr:
    __ssh_connect_timeout_S = 1

    @staticmethod
    def Instance():
        return _instance
        
    def __init__(self):
        self.__ssh_dict = {}

    def open_ssh(self, ip:str, user:str, passwd:str):
        """
        初始化某个SSH
        xxx = SSH_Mgr().Instance().open_ssh("192.168.8.146", "sat", "123456")

        Return:
        None:连接失败
        ssh_context:连接成功
        """
        
        # id = "{}_{}".format(ip, user)
        # ssh_context = self.__ssh_dict.get(id)
        # if ssh_context != None:
        #     logger.info("{} Already Connected. Connect Success".format(id))
        #     return ssh_context
        
        # self.__ssh_dict.pop(id, None)

        try:
            # ssh_context = ssh(host=ip, user=user, password=passwd, 
            #                   level=logging.ERROR,
            #                   timeout = SSH_Mgr.__ssh_connect_timeout_S)
            # info = ssh_context.checksec()
            sshcmd = 'sshpass -p "{}" ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no {}@{}'.format(passwd,user,ip)
            ssh_context = process(["sh","-c",sshcmd])
            logger.info("SSH Connect {} Success.Info:\n{}".format(id, info))

            # self.__ssh_dict[id] = ssh_context
            return ssh_context
        except Exception as err:
            logger.exception("SSH Connect {} Fail!".format(id))
            return None  


    def close_ssh(self, ssh_context:ssh):
        """
        关闭某个SSH
        xxx = SSH_Mgr().Instance().open_ssh("192.168.8.146", "sat", "123456")
        SSH_Mgr().Instance().close_ssh(xxx)
        """

        if ssh_context == None:
            logger.error("SSH Context Invalid!")
            return

        id = "{}_{}".format(ssh_context.host, ssh_context.user)
        self.__ssh_dict.pop(id, None)
        logger.info("SSH Context {} Delete Success.".format(id))        
        if ssh_context.connected() == True:
            ssh_context.close()
            logger.info("SSH Close {} Success.".format(id))
        
        return


    def ssh_cmd(self, ssh_context:ssh, ssh_cmd:str):
        """
        发送自定义ssh命令
        xxx = SSH_Mgr().Instance().open_ssh("192.168.225.1", "root", "xx")
        SSH_Mgr().Instance().ssh_cmd(xxx, ["ls","-l"])

        Return:
总计 48
drwxr-xr-x 2 sat sat 4096 11月 9日 14:23 公共
....
        """
        if ssh_context == None:
            logger.error("SSH Context Invalid!")
            return None
        
        id = "{}_{}".format(ssh_context.host, ssh_context.user)
        if ssh_context.connected() != True:
            logger.error("SSH {} Not Connect. Please Reconect.".format(id))
            return None
        
        try:
            cmd_result = ssh_context.system(ssh_cmd).recvall().decode('utf-8')
            logger.info("SSH {} Run CMD {} Success. Result:\n{}".format(id, ssh_cmd, cmd_result))
            return cmd_result
        
        except Exception as err:
            logger.exception("SSH {} Run CMD {} Fail!".format(id, ssh_cmd))
            return None


_instance = SSH_Mgr()

