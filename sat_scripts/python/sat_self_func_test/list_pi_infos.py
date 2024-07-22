#!/usr/bin/env python
import logging
logger = logging.getLogger(__name__)

from sat_toolkit.tools.pi_mgr import Pi_Mgr


def main():
    Pi_Mgr.Instance().uname()
    Pi_Mgr.Instance().hostname()

if __name__ == '__main__':
    main()