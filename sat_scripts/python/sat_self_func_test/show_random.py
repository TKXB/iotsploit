#!/usr/bin/env python
import logging
logger = logging.getLogger(__name__)
import random

def main():
    a = random.random()
    logger.info("Random:{}".format(a))

if __name__ == '__main__':
    main()