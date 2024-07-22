#!/usr/bin/env python
import logging
logger = logging.getLogger(__name__)

import usb


def main():
    usb_devices = usb.core.show_devices()
    logger.info(usb_devices)

if __name__ == '__main__':
    main()