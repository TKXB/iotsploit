import logging
from sat_toolkit.tools.ssh_mgr import Ssh_Mgr
from sat_toolkit.tools.env_mgr import Env_Mgr
logger = logging.getLogger(__name__)

logger.info("ssh to tcam ...")

ssh_VehicleModel = Env_Mgr.Instance().get("__SAT_ENV__VehicleInfo_VehicleModel")
ssh_VehicleModel=ssh_VehicleModel[15:]
ssh_passwd = Env_Mgr.Instance().get("__SAT_ENV__VehicleInfo_TCAM_SSH_Passwd")#后面需要加环境变量
if(ssh_VehicleModel =="BX1E"):
    Ssh_Mgr().Instance.open_ssh("192.168.225.1","root","xxxx")
else if (ssh_VehicleModel == ""):
    Ssh_Mgr().Instance.open_ssh("192.168.15.1","root","xxxx")