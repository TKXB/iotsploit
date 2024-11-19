# addx 20231117-14:34
# Teststep:用户交互||请确认USB设备已经插入
import logging
from sat_toolkit.tools.input_mgr import Input_Mgr
logger = logging.getLogger(__name__)

def main():
    logger.info("请确认USB设备是否已经插入，完成/未完成:Y/N")
    user_input = Input_Mgr.string_input()
    if user_input == "Y" or user_input == "y":
        return 1,"用户已确认完成"
    else:
        return -1,"用户未完成"

if __name__ == '__main__':
    main()