import logging
logger = logging.getLogger(__name__)
import time
from sat_toolkit.tools.sat_utils import *
from sat_toolkit.tools.vehicle_utils import *

from sat_toolkit.tools.input_mgr import Input_Mgr

from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.wifi_mgr import WiFi_Mgr

def main():
    connect_tcam_wifi()

if __name__ == '__main__':
    main()