import logging
logger = logging.getLogger(__name__)
import time

class SAT_Exception(Exception):
    ERROR__ERRORCODE__START = 0
    FAIL__ERRORCODE__START = -10000



    def __init__(self, err_code, err_msg):
        super().__init__()
        self.err_code = err_code
        self.err_msg = err_msg
        logger.error(err_msg)

def raise_err(err_msg):
    raise SAT_Exception(SAT_Exception.ERROR__ERRORCODE__START -1, err_msg)


def raise_ok(err_msg):
    raise SAT_Exception(1, err_msg)
def raise_no(err_msg):
    raise SAT_Exception(SAT_Exception.FAIL__ERRORCODE__START -1, err_msg)

def sat_sleep(second):
    time.sleep(second)

def calculate_time_difference(before, after):
    diff = after - before
    hours = diff.seconds // 3600
    minutes = (diff.seconds // 60) % 60
    seconds = diff.seconds % 60

    return "{}小时{}分{}秒".format(hours, minutes, seconds)    