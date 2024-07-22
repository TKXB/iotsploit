import logging
logger = logging.getLogger(__name__)

from sat_toolkit.tools.input_mgr import Input_Mgr

from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.doip_mgr import DoIP_Mgr
from sat_toolkit.tools.sat_utils import *

def main(debug_mode:str,ecu:str):
    # Input_Mgr.Instance().confirm("请确认OBD已经通过DoIP连接SAT")
    if debug_mode == "open":
        DoIP_Mgr.Instance().opendebug(ecu)
    elif debug_mode == "close":
        DoIP_Mgr.Instance().closedebug(ecu)
    else:
        raise_err( "DoIP模式:{} 不支持!".format(debug_mode))

    raise_ok("DoIP DebugMode:{},ecu {}".format(debug_mode,ecu))

if __name__ == '__main__':
    main()