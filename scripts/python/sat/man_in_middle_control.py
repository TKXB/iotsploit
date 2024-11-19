import logging
logger = logging.getLogger(__name__)

import time

def loginfo_return(return_code, err_msa):
    logger.info(err_msa)
    return return_code, err_msa

def main(control:str):
    time.sleep(1)
    raise_ok( "man_in_middle_control功能尚未实现. control:{}".control)

if __name__ == '__main__':
    main()