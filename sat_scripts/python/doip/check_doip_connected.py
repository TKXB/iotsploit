import logging
logger = logging.getLogger(__name__)

from sat_toolkit.tools.input_mgr import Input_Mgr

from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.doip_mgr import DoIP_Mgr
from sat_toolkit.tools.sat_utils import *

def main():
    # Input_Mgr.Instance().confirm("请确认OBD线连接SAT")
    if DoIP_Mgr.Instance().connect():
        DoIP_Mgr.Instance().disconnect()
        raise_ok("DoIP已连接")
    raise_err("DoIP未连接")
if __name__ == '__main__':
    main()