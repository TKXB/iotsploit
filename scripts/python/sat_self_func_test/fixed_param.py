#!/usr/bin/env python
import logging
logger = logging.getLogger(__name__)

def main(p1, p2, p3, p4):
    logger.info("Param1:{}".format(p1))
    logger.info("Param2:{}".format(p2))
    logger.info("Param3:{}".format(p3))
    logger.info("Param4:{}".format(p4))


if __name__ == '__main__':
    main()