import logging
logger = logging.getLogger(__name__)

from sat_toolkit.tools.input_mgr import Input_Mgr

from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.doip_mgr import DoIP_Mgr
from sat_toolkit.tools.sat_utils import *
from sat_toolkit.tools.bash_script_engine import Bash_Script_Mgr

import scripts.python.ip_port_scan
def main():
    #删除路由
    route_cmds = Env_Mgr.Instance().query(scripts.python.ip_port_scan.DEL_ROUTES_CMDS,[])
    for cmd in route_cmds:
        Bash_Script_Mgr.Instance().exec_cmd(cmd)
    Env_Mgr.Instance().set(scripts.python.ip_port_scan.DEL_ROUTES_CMDS,[])
if __name__ == '__main__':
    main()