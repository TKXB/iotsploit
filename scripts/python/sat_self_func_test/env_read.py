#!/usr/bin/env python
import logging
logger = logging.getLogger(__name__)

from sat_toolkit.tools.env_mgr import Env_Mgr

def main(p1):
    Env_Mgr.Instance().dump()

    logger.info("Param1:{}".format(p1))
    logger.info("READ __SAT_ENV__VehicleInfo_ID:{}".format(Env_Mgr.Instance().get("__SAT_ENV__VehicleInfo_ID")))
    logger.info("READ NO_SUCH_ENV:{}".format(Env_Mgr.Instance().get("NO_SUCH_ENV","THIS IS DEFAULT VALUE")))
    logger.info("Param READ {}:{}".format(p1, Env_Mgr.Instance().get(p1,"THIS IS DEFAULT VALUE")))

if __name__ == '__main__':
    main()