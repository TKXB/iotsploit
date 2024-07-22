#!/usr/bin/env python
import logging
logger = logging.getLogger(__name__)

from sat_toolkit.tools.env_mgr import Env_Mgr

def main(key, value):
    logger.info("ALL ENV Before Update")
    Env_Mgr.Instance().dump()

    logger.info("Update {}={}".format(key, value))
    Env_Mgr.Instance().set(key, value)

    logger.info("ALL ENV After Update")
    Env_Mgr.Instance().dump()

    logger.info("Delete {}".format(key))
    Env_Mgr.Instance().unset(key)

    logger.info("ALL ENV After Delete")
    Env_Mgr.Instance().dump()

if __name__ == '__main__':
    main()