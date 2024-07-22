import logging
logger = logging.getLogger(__name__)

from sat_toolkit.tools.input_mgr import Input_Mgr

def main(confirm_str:str):
    Input_Mgr.Instance().confirm(confirm_str)
    
if __name__ == '__main__':
    main()