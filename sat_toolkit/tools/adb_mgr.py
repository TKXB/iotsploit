import logging
logger = logging.getLogger(__name__)

from sat_toolkit.tools.env_mgr import Env_Mgr
from sat_toolkit.tools.usb_mgr import USB_Mgr
from sat_toolkit.tools.sat_utils import *
from sat_toolkit.tools.bash_script_engine import Bash_Script_Mgr

from pwnlib import term
term.term_mode = True
from pwn import *
from pwnlib.exception import PwnlibException


class ADB_Mgr:
    DHU_ADB_SERIAL = "__DTU_ADB_SERIAL_ID__"
    TCAM_ADB_SERIAL = "__TCAM_ADB_SERIAL_ID__"
    __temp_script_file_path = "/data/local/tmp/__Zeekr_SAT_TMP_FILES/tmp_bash_script.sh"

    @staticmethod
    def Instance():
        return _instance
        
    def __init__(self):
        self.__last_connect_serial = None
        self.__last_adb_root = None
        pass
    def init_adb_service(self):
        #adb_mgr 必须在主线程里面初始化
        logger.info("Init ADB Services As Root")
        # adb.root()
        # self.__last_adb_root = True
        self.list_devices()

    def query_dhu_adb_serial_id(self):
        vehicle_dhu_serial = Env_Mgr.Instance().query("__SAT_ENV__VehicleInfo_DHU_ADB_SERIAL_ID")
        if vehicle_dhu_serial != None and len(vehicle_dhu_serial) != 0:
            logger.info("DHU ADB SERIAL ID Found IN ENV:{}".format(vehicle_dhu_serial))
            return vehicle_dhu_serial

        logger.info("DHU ADB SERIAL ID NOT Found IN ENV! Use DHU_USB_VendorID AND DHU_USB_ProductID Instead")
        DHU_USB_VendorID = Env_Mgr.Instance().get("__SAT_ENV__VehicleModel_DHU_USB_VendorID")
        DHU_USB_ProductID = Env_Mgr.Instance().get("__SAT_ENV__VehicleModel_DHU_USB_ProductID")
        logger.info("DHU_USB_VendorID:{}  DHU_USB_ProductID:{}".format(DHU_USB_VendorID, DHU_USB_ProductID))

        for usb in USB_Mgr.Instance().list_usb_devices():
            if usb["idVendor"] == int(DHU_USB_VendorID, 16)  and usb["idProduct"] == int(DHU_USB_ProductID, 16):
                logger.info("Find DHU USB In USB List:{}".format(usb))
                return usb["iSerialNumber"]
            
        raise_err( "DHU ADB Serial ID 查询失败! 连接的USB设备中没有找到匹配设备")


    def query_tcam_adb_serial_id(self):
        vehicle_tcam_serial = Env_Mgr.Instance().query("__SAT_ENV__VehicleInfo_TCAM_ADB_SERIAL_ID")
        if vehicle_tcam_serial != None and len(vehicle_tcam_serial) != 0:
            logger.info("TCAM ADB SERIAL ID IN ENV:{}".format(vehicle_tcam_serial))
            return vehicle_tcam_serial
        
        logger.info("TCAM ADB SERIAL ID NOT Found IN ENV! Use TCAM_USB_VendorID AND TCAM_USB_ProductID Instead")
        TCAM_USB_VendorID = Env_Mgr.Instance().get("__SAT_ENV__VehicleModel_TCAM_USB_VendorID")
        TCAM_USB_ProductID = Env_Mgr.Instance().get("__SAT_ENV__VehicleModel_TCAM_USB_ProductID")
        logger.info("TCAM_USB_VendorID:{}  TCAM_USB_ProductID:{}".format(TCAM_USB_VendorID, TCAM_USB_ProductID))
        
        for usb in USB_Mgr.Instance().list_usb_devices():
            if usb["idVendor"] == int(TCAM_USB_VendorID, 16)  and usb["idProduct"] == int(TCAM_USB_ProductID, 16):            
                logger.info("Find TCAM USB In USB List:{}".format(usb))
                return usb["iSerialNumber"]
            
        raise_err( "TCAM ADB Serial ID 查询失败! 连接的USB设备中没有找到匹配设备")

    def __recheck_device_serial(self, device_serial:str):
        if device_serial == ADB_Mgr.DHU_ADB_SERIAL:
            device_serial = self.query_dhu_adb_serial_id()
        if device_serial == ADB_Mgr.TCAM_ADB_SERIAL:
            device_serial = self.query_tcam_adb_serial_id()

        if device_serial == None:
            raise_err( "Device Serial:{} Invalid!".format(device_serial))
        
        return device_serial

    def check_connect_status(self, device_serial:str):
        if device_serial == None:
            raise_err( "Device Serial Invalid!")

        if device_serial == ADB_Mgr.DHU_ADB_SERIAL:
            device_serial_checked = Env_Mgr.Instance().query("__SAT_ENV__VehicleInfo_DHU_ADB_SERIAL_ID")
            if device_serial_checked == None or len(device_serial_checked) == 0: 
                logger.info("DHU ADB SERIAL ID NOT Found IN ENV! Use DHU_USB_VendorID AND DHU_USB_ProductID Instead")

                device_serial_checked = None
                DHU_USB_VendorID = Env_Mgr.Instance().get("__SAT_ENV__VehicleModel_DHU_USB_VendorID")
                DHU_USB_ProductID = Env_Mgr.Instance().get("__SAT_ENV__VehicleModel_DHU_USB_ProductID")
                logger.info("DHU_USB_VendorID:{}  DHU_USB_ProductID:{}".format(DHU_USB_VendorID, DHU_USB_ProductID))
                
                for usb in USB_Mgr.Instance().list_usb_devices():
                    if usb["idVendor"] == int(DHU_USB_VendorID, 16)  and usb["idProduct"] == int(DHU_USB_ProductID, 16):                    
                        logger.info("Find DHU USB In USB List:{}".format(usb))
                        device_serial_checked = usb["iSerialNumber"]
                        break
                if device_serial_checked == None:
                    logger.info("DHU USB Not Found In USB List:")
                    return False
            else:
                logger.info("DHU ADB SERIAL ID Found IN ENV:{}".format(device_serial_checked))

        elif device_serial == ADB_Mgr.TCAM_ADB_SERIAL:
            device_serial_checked = Env_Mgr.Instance().query("__SAT_ENV__VehicleInfo_TCAM_ADB_SERIAL_ID")
            if device_serial_checked == None or len(device_serial_checked) == 0:  
                logger.info("TCAM ADB SERIAL ID NOT Found IN ENV! Use TCAM_USB_VendorID AND TCAM_USB_ProductID Instead")

                device_serial_checked = None
                TCAM_USB_VendorID = Env_Mgr.Instance().get("__SAT_ENV__VehicleModel_TCAM_USB_VendorID")
                TCAM_USB_ProductID = Env_Mgr.Instance().get("__SAT_ENV__VehicleModel_TCAM_USB_ProductID")
                logger.info("TCAM_USB_VendorID:{}  TCAM_USB_ProductID:{}".format(TCAM_USB_VendorID, TCAM_USB_ProductID))

                for usb in USB_Mgr.Instance().list_usb_devices():
                    if usb["idVendor"] == int(TCAM_USB_VendorID, 16)  and usb["idProduct"] == int(TCAM_USB_ProductID, 16):
                        logger.info("Find TCAM USB In USB List:{}".format(usb))
                        device_serial_checked = usb["iSerialNumber"]
                        break
                if device_serial_checked == None:
                    logger.info("TCAM USB Not Found In USB List:")
                    return False
            else:
                logger.info("TCAM ADB SERIAL ID Found IN ENV:{}".format(device_serial_checked))
        else:
            device_serial_checked = device_serial

        adb_devices = ADB_Mgr.Instance().list_devices()
        for dev in adb_devices:
            if dev.serial == device_serial_checked:
                logger.info("Find Serial IN ADB:{}".format(dev))
                return True
        logger.info("Serial:{} Not Found IN ADB Devices".format(device_serial_checked))
        return False


    def list_devices(self):
        """
        检查查adb连接情况
        ADB_Mgr.Instance().list_devices()
        Return:
        AdbDevice(serial='A2VCBB1C02004686', type='device', port=None, product='KKG-AN70', model='KKG AN70',device='HNKKG-M'),
        AdbDevice(serial='A2VCBB1C02004686', type='device', port=None, product='KKG-AN70', model='KKG AN70',device='HNKKG-M'),
        AdbDevice(serial='A2VCBB1C02004686', type='device', port=None, product='KKG-AN70', model='KKG AN70',device='HNKKG-M')
        """
        try:
            device_list = adb.devices()
            logger.info("Curr ADB Devices Count:{}\n{}".format(len(device_list), device_list))

        except pwnlib.exception.PwnlibException as e:
            if "'./adb' does not exist" in str(e):
                logger.error("ADB not found. Please install ADB and add it to your PATH")
            else:
                logger.error(f"ADB connection error: {str(e)}")
            device_list = []
        except Exception as err:
            logger.exception("ADB List Devices Fail!")
            device_list = []     
        
        return device_list

    def connect_dev(self, device_serial:str, root_require=False, force_unroot = False):
        """
        adb shell连接设备,是否root，root密码
        ADB_Mgr().Instance().connect_dev("c4f165f7", True)

        Return:
        None:   设备不存在
        device:  连接成功的设备
        """

        device_serial_checked = self.__recheck_device_serial(device_serial)
        need_reconnect = False
        if device_serial_checked != self.__last_connect_serial:
            need_reconnect = True
        if root_require == True and self.__last_adb_root == False:
            need_reconnect = True
        if root_require == False and force_unroot == True and self.__last_adb_root == True:
            need_reconnect = True

        if need_reconnect == False:
            logger.info("Curr:{}_{} Need:{}_{}_{} Match Require. Skip".format(
                self.__last_connect_serial, self.__last_adb_root,
                device_serial_checked, root_require, force_unroot))
            return self.__last_connect_serial

        logger.info("Curr:{}_{} Need:{}_{}_{} ADB Connect Start".format(
            self.__last_connect_serial, self.__last_adb_root,
            device_serial_checked, root_require, force_unroot))

        self.__last_connect_serial = None
        self.__last_adb_root = None

        try:
            device_list = self.list_devices()
            target_dev = None
            for dev in device_list:
                if dev.serial == device_serial_checked:
                    target_dev = dev
                    break
            
            if target_dev != None:
                logger.info("ADB Find Device Success: {}".format(target_dev))
            else:
                logger.error("ADB Find Device Fail! Serial:{} Not Found".format(device_serial_checked))
                return None

            context.device = device_serial_checked
            adb.wait_for_device()

            logger.info("ADB Connect Device Success: {}".format(target_dev))
        except Exception as err:
            logger.error("ADB Connect Device Fail! Connect Abort")
            return None  

        if root_require == True:
            logger.info("ADB Root Required.")
            if self.__last_adb_root != True:
                try:
                    adb.root()
                    sat_sleep(2)
                    logger.info("ADB Root Required. Restart ADBD As Root.")
                    self.__last_adb_root = True
                except Exception as err:
                    logger.error("ADB Root Fail! Connect Abort")
                    self.__last_adb_root = None
                    return None
            else:
                logger.info("ADB Already Rooted")
        else:
            if force_unroot == True:
                logger.info("ADB Force UnRoot Required.")
                if self.__last_adb_root != False:
                    try:
                        adb.unroot() 
                        sat_sleep(2)
                        logger.info("ADB Root NOT Required. Restart ADBD As Shell.")
                        self.__last_adb_root = False
                    except Exception as err:
                        self.__last_adb_root = None
                        logger.exception("ADB UnRoot Request Fail! Connect Abort.")
                        return None
                else:
                    logger.info("ADB Already UnRooted")
            else:
                logger.info("ADB Force UnRoot NOT Required.")
                if self.__last_adb_root == None:
                    logger.info("Default ADB  Treat As Shell.")
                    self.__last_adb_root = False
                    # try:
                    #     adb.root()
                    #     sat_sleep(2)
                    #     logger.info("Force ADB Root. Restart ADBD As Root.")
                    #     self.__last_adb_root = True
                    # except Exception as err:
                    #     logger.error("ADB Root Fail! Connect Abort")
                    #     self.__last_adb_root = None
                    #     return None

    
        self.__last_connect_serial = device_serial_checked

        return self.__last_connect_serial


    def pull_file(self, device_serial:str, android_file_path:str, sat_file_path:str):
        """
        adb pull file 默认ROOT连接
        ADB_Mgr.Instance().pull_file(ADB_Mgr.TCAM_ADB_SERIAL, "/proc/version", "./proc_version")

        Return:
        -1: 设备之前没有连接成功
        -2: 文件没有权限读取
        1:  操作成功
        """
        con_dev = self.connect_dev(device_serial, True)
        if con_dev == None:
            raise_err( "Device {} Connect Fail!".format(device_serial))

        try:
            adb.pull(android_file_path, sat_file_path)
            logger.info("Device:{} Pull File {} -> {} Success.".format(device_serial, android_file_path, sat_file_path))
            return 1
        except Exception as err:
            logger.exception("Device:{} Pull File {} -> {} Fail!".format(device_serial, android_file_path, sat_file_path))
            return -2
    
    def push_file(self, device_serial:str, sat_file_path:str, android_file_path:str):
        """
        adb push file 默认ROOT连接
        ADB_Mgr().Instance().connect_dev("A2VCBB1C02004686")
        ADB_Mgr.Instance().push_file("A2VCBB1C02004686","./proc_version", "")

        Return:
        -1: 设备之前没有连接成功
        -2: 文件没有权限写入
        1:  操作成功
        """

        con_dev = self.connect_dev(device_serial, True)
        if con_dev == None:
            raise_err( "Device {} Connect Fail!".format(device_serial))

        try:
            adb.push(sat_file_path, android_file_path)
            logger.info("Device:{} Push File {} -> {} Success.".format(device_serial, sat_file_path, android_file_path))
            return 1
        except Exception as err:
            logger.exception("Device:{} Push File {} -> {} Fail!".format(device_serial, sat_file_path, android_file_path))
            return -2

    def list_installed_apps(self, device_serial:str):
        """
        列出app安装列表 默认ROOT连接
        ADB_Mgr().Instance().connect_dev("A2VCBB1C02004686")
        ADB_Mgr.Instance().list_installed_apps("A2VCBB1C02004686")

        Return:
        None: 设备之前没有连接成功或者其他失败
        list: APP列表
        ['com.mediatek.ims', 'cn.wps.moffice_eng']        
        """

        con_dev = self.connect_dev(device_serial)
        if con_dev == None:
            raise_err( "Device {} Connect Fail!".format(device_serial))
        
        try:
            app_list = []
            packages = adb.process(['pm', 'list', 'packages']).recvall().decode('utf-8')
            for package_line in packages.splitlines():
                app_list.append(package_line.replace("package:", ""))
            logger.info("Device:{} List Installed APPs Success. APPs:{}".format(device_serial, app_list))
            return app_list
        
        except Exception as err:
            logger.exception("Device:{} List Installed APPs Fail!".format(device_serial))
            return None

    def query_dir_status(self, device_serial:str, dir_path:str):
        """
        查询某个目录的信息ls -l  默认ROOT连接
        ADB_Mgr().Instance().connect_dev("A2VCBB1C02004686")
        ADB_Mgr.Instance().query_dir_status('a8d1de6f',"/")

        Return:
        None: 设备之前没有连接成功或者其他失败
        list: 目录内文件详情列表
        []
        [{'type': 'drwx------', 'owner': 'u0_a120:u0_a120', 'name': 'cloudmusic'}, {'type': 'drwx------', 'owner': '3:u0_a120', 'name': 'ichat'}, {'type': 'drwx------', 'owner': '2:u0_a120', 'name': 'nmvideocreator'}, {'type': 'drwx------', 'owner': '3:u0_a120', 'name': 'publish'}]
        """

        con_dev = self.connect_dev(device_serial, True)
        if con_dev == None:
            raise_err( "Device {} Connect Fail!".format(device_serial))
        
        try:
            result_list = []
            results = adb.process(['ls', '-l', dir_path]).recvall().decode('utf-8')
            if results.startswith("total "):
                for line in results.splitlines()[1:]:
                    item_dict = {}
                    # drwx------  2 u0_a120 u0_a120 3452 2022-08-02 00:11 nmvideocreator
                    content_list = line.split(" ")
                    item_dict["type"] = content_list[0]
                    item_dict["owner"] = content_list[2] + ":"+ content_list[3]
                    item_dict["name"] = content_list[-1]
                    result_list.append(item_dict)

                logger.info("Device:{} List Query Dir:{} Success. Dir Status:{}".format(device_serial, dir_path, result_list))
                return result_list

            else:
                logger.info("Device:{} List Query Dir:{} Fail! Dir Not Exists.".format(device_serial, dir_path))
                return []
        
        except Exception as err:
            logger.exception("Device:{} List Query Dir:{} Fail! ADB Cmd Fail!".format(device_serial, dir_path))
            return None

    def shell_cmd(self, device_serial:str, cmd:str, root_required=True):
        """
        执行shell_cmd  默认ROOT连接
        
        """
        if root_required:
            con_dev = self.connect_dev(device_serial, True)
            if con_dev == None:
                raise_err( "Device {} Connect Fail!".format(device_serial))
        else:
            con_dev = self.connect_dev(device_serial, False)
            if con_dev == None:
                raise_err( "Device {} Connect Fail!".format(device_serial))

        logger.info("Device:{} Execute Shell CMD:{} Start -->>".format(device_serial, cmd))
        adb.makedirs(os.path.dirname(ADB_Mgr.__temp_script_file_path))
        adb.write(ADB_Mgr.__temp_script_file_path, cmd)
        results = adb.process(["sh", ADB_Mgr.__temp_script_file_path]).recvall().decode('utf-8')        
        # results = adb.process(["sh", ADB_Mgr.__temp_script_file_path, ">"," {}.log".format(ADB_Mgr.__temp_script_file_path),
        #                        ";" ," cat", " {}.log".format(ADB_Mgr.__temp_script_file_path)]).recvall().decode('utf-8')
        logger.info("Device:{} Execute Shell CMD:{} Finish -->>".format(device_serial, cmd))

        return results


    def query_dirs_permission_writable_by_any_user(self,device_serial:str,finddir:str,namefilter:str,passdirs:list,passsids:list):
        """
        查查找任意用户可写文件  默认ROOT连接
        ADB_Mgr().Instance().connect_dev("c4f165f7", True)
        ADB_Mgr.Instance().query_dirs_permission_writable_by_any_user('c4f165f7')

        Return:
        """
        con_dev = self.connect_dev(device_serial, True)
        if con_dev == None:
            raise_err( "Device {} Connect Fail!".format(device_serial))            

        try:
            # results = self.shell_cmd(device_serial, "find / -perm -2 -type d -print0 2> /dev/null | xargs -0 -r ls -d -l -Z 2>/dev/null")
            results = ""
            if namefilter == "":
                results = self.shell_cmd(device_serial, "find {} -perm -2 -type d -print0  2>/dev/null | xargs -0 -r ls -d -l -Z 2>/dev/null".format(finddir))
            else:
                results = self.shell_cmd(device_serial, "find {} -perm -2 -type d -name \"{}\" -print0  2>/dev/null | xargs -0 -r ls -d -l -Z 2>/dev/null".format(finddir,namefilter))
            hasSelinux = ADB_Mgr.Instance().query_android_selinux_status(ADB_Mgr.DHU_ADB_SERIAL)

            dirs = []
            allowdirs = self.query_writable_mount_dirs(device_serial)
            logger.info("results:{}".format(results))
            logger.info("allowdirs:{}".format(allowdirs))
            #drwxrwxrwx 5 root   root   u:object_r:unlabeled:s0                               4096 2023-12-06 19:23 /nfs_share
            itemregx = re.compile("(\S+)\s+\S+\s+(\S+)\s+(\S+)\s+(\S+)\s+\S+\s+\S+\s+\S+\s+(.*)")
            for item in results.splitlines():
                finditem = itemregx.findall(item)
                rwx = finditem[0][0]
                owner = finditem[0][1]
                group = finditem[0][2]
                sid = finditem[0][3]
                dirpath = finditem[0][4] + "/"
                #过滤掉虚拟目录/dev/ /proc/ /sys/ 这些
                isPass = False
                for dir in passdirs:
                    if dirpath.startswith(dir):
                        isPass = True
                        break
                if isPass:
                    continue
                isPass = True
                for dir in allowdirs:
                    if dirpath.startswith(dir):
                        isPass = False
                        break
                if isPass:
                    continue
                if hasSelinux:
                    for passsid in passsids:
                        if passsid in sid:
                            isPass = True
                            break
                if isPass:
                    continue
                dirs.append({"rwx":rwx,"owner":owner,"group":group,"sid":sid,"dirpath":dirpath})
            #drwxrwxrwx 1 ccc ccc ? 4096 Nov  6 11:13 /mnt/c/Intel
            # itemregx = re.compile("(.+) (.+) (.+) (.+) (.+) (.+) (.+)  (.+) (.+) (.+)")
            # for item in results.splitlines():
            #     fields = itemregx.findall(item)
            #到车上看看
            #过滤掉虚拟目录/dev/ /proc/ /sys/ 这些
            logger.info("Device:{} Query Dirs Permissions Success. Result:{}".format(device_serial, results))
            return dirs
        
        except Exception as err:
            logger.exception("Device:{} query_files_permission Fail! ADB Cmd Fail!".format(device_serial))
            return None
        
    def query_writable_mount_dirs(self, device_serial:str):
        con_dev = self.connect_dev(device_serial, True)
        if con_dev == None:
            raise_err( "Device {} Connect Fail!".format(device_serial))     

        try:
            results = self.shell_cmd(device_serial, "mount |grep rw|grep -v function|grep -v tmpfs|grep -v bpf|grep -v binder|grep -v configfs|grep -v tracefs|grep -v cgroup|grep -v selinuxfs|grep -v proc|grep -v devpts|grep -v sysfs")
            logger.info(results)
            dirs = []
            itemre = re.compile("on\s+(\S+)")
            for item in results.splitlines():
                finditem = itemre.findall(item)
                logger.info(finditem)
                dirs.append(finditem[0]+"/")
            # logger.info("results:{}".format(results))
            return dirs
        except Exception as err:
            logger.exception("Device:{} query monut Fail! ADB Cmd Fail!".format(device_serial))
            return None

    def query_files_permission_readable_by_any_user(self, device_serial:str,finddir:str,namefilter:str,passdirs:list,passsids:list):
        """
        查查找任意用户可写文件  默认ROOT连接
        ADB_Mgr().Instance().connect_dev("a8d1de6f")
        ADB_Mgr.Instance().query_files_permission_writable_by_any_user('a8d1de6f')

        Return:
        """
        con_dev = self.connect_dev(device_serial, True)
        if con_dev == None:
            raise_err( "Device {} Connect Fail!".format(device_serial))     
        try:
            results = ""
            if namefilter == "":
                results = self.shell_cmd(device_serial, "find {} -perm -4 -type f -print0  2>/dev/null | xargs -0 -r ls -l -Z 2>/dev/null".format(finddir))
            else:
                results = self.shell_cmd(device_serial, "find {} -perm -4 -type f -name \"{}\" -print0  2>/dev/null | xargs -0 -r ls -l -Z 2>/dev/null".format(finddir,namefilter))
            hasSelinux = ADB_Mgr.Instance().query_android_selinux_status(ADB_Mgr.DHU_ADB_SERIAL)
            logger.info("results:{}".format(results))
            #-rw-rw-rw- 1 system          system         u:r:system_app:s0                                           0 2023-12-08 17:37:44.559987883 +0800 /proc/3677/task/3677/attr/exec
            files = []
            itemregx = re.compile("(\S+)\s+\S+\s+(\S+)\s+(\S+)\s+(\S+)\s+\S+\s+\S+\s+\S+\s+(.*)")
            for item in results.splitlines():
                finditem = itemregx.findall(item)
                rwx = finditem[0][0]
                owner = finditem[0][1]
                group = finditem[0][2]
                sid = finditem[0][3]
                filepath = finditem[0][4]
                #过滤掉虚拟目录/dev/ /proc/ /sys/ 这些
                isPass = False
                for dir in passdirs:
                    if filepath.startswith(dir):
                        isPass = True
                        break
                if isPass:
                    continue
                if hasSelinux:
                    for passsid in passsids:
                        if passsid in sid:
                            isPass = True
                            break
                if isPass:
                    continue
                files.append({"rwx":rwx,"owner":owner,"group":group,"sid":sid,"filepath":filepath})
            # #到车上看看
            # logger.info("Device:{} Query Files Permissions Success. Result:{}".format(device_serial, files))
            return files
        
        except Exception as err:
            logger.exception("Device:{} query_files_permission Fail! ADB Cmd Fail!".format(device_serial))
            return None

 
    def query_files_permission_writable_by_any_user(self, device_serial:str,finddir:str,namefilter:str,passdirs:list,passsids:list):
        """
        查查找任意用户可写文件  默认ROOT连接
        ADB_Mgr().Instance().connect_dev("a8d1de6f")
        ADB_Mgr.Instance().query_files_permission_writable_by_any_user('a8d1de6f')
        Return:
        """
        con_dev = self.connect_dev(device_serial, True)
        if con_dev == None:
            raise_err( "Device {} Connect Fail!".format(device_serial))     

        try:
            results = ""
            if namefilter == "":
                results = self.shell_cmd(device_serial, "find {} -perm -2 -type f -print0  2>/dev/null | xargs -0 -r ls -l -Z 2>/dev/null".format(finddir))
            else:
                results = self.shell_cmd(device_serial, "find {} -perm -2 -type f -name \"{}\" -print0  2>/dev/null | xargs -0 -r ls -l -Z 2>/dev/null".format(finddir,namefilter))
            hasSelinux = ADB_Mgr.Instance().query_android_selinux_status(ADB_Mgr.DHU_ADB_SERIAL)
            allowdirs = self.query_writable_mount_dirs(device_serial)
            logger.info("results:{}".format(results))
            logger.info("allowdirs:{}".format(allowdirs))
            #-rw-rw-rw- 1 system          system         u:r:system_app:s0                                           0 2023-12-08 17:37:44.559987883 +0800 /proc/3677/task/3677/attr/exec
            files = []
            itemregx = re.compile("(\S+)\s+\S+\s+(\S+)\s+(\S+)\s+(\S+)\s+\S+\s+\S+\s+\S+\s+(.*)")
            for item in results.splitlines():
                finditem = itemregx.findall(item)
                rwx = finditem[0][0]
                owner = finditem[0][1]
                group = finditem[0][2]
                sid = finditem[0][3]
                filepath = finditem[0][4]
                #过滤掉虚拟目录/dev/ /proc/ /sys/ 这些
                isPass = False
                for dir in passdirs:
                    if filepath.startswith(dir):
                        isPass = True
                        break
                if isPass:
                    continue
                isPass = True
                for dir in allowdirs:
                    if filepath.startswith(dir):
                        isPass = False
                        break
                if isPass:
                    continue
                if hasSelinux:
                    for passsid in passsids:
                        if passsid in sid:
                            isPass = True
                            break
                if isPass:
                    continue
                files.append({"rwx":rwx,"owner":owner,"group":group,"sid":sid,"filepath":filepath})
            # #到车上看看
            # logger.info("Device:{} Query Files Permissions Success. Result:{}".format(device_serial, files))
            return files
        
        except Exception as err:
            logger.exception("Device:{} query_files_permission Fail! ADB Cmd Fail!".format(device_serial))
            return None
        

    def query_files_permission_suid(self, device_serial:str):
        #ADB_Mgr().Instance().connect_dev("A2VCBB1C02004686")
        #ADB_Mgr.Instance().query_files_permission_suid('c4f165f7')
        #
        """
        查找任意Suid权限文件/文件夹
        Return:
        """
        con_dev = self.connect_dev(device_serial, True)
        if con_dev == None:
            raise_err( "Device {} Connect Fail!".format(device_serial))     

        try:
            results = self.shell_cmd(device_serial, "find / -perm -4000 -print0 2>/dev/null | xargs -0 -r ls -l -Z 2>/dev/null")
            logger.info("results:{}".format(results))            
            files = []
            #-rwsr-x--- 1 root shell u:object_r:su_exec:s0  11088 2023-12-02 04:25 /system/xbin/su
            itemregx = re.compile("(\S+)\s+\S+\s+(\S+)\s+(\S+)\s+(\S+)\s+\S+\s+\S+\s+\S+\s+(.*)")
            for item in results.splitlines():
                finditem = itemregx.findall(item)
                rwx = finditem[0][0]
                owner = finditem[0][1]
                group = finditem[0][2]
                sid = finditem[0][3]
                filepath = finditem[0][4]
                files.append({"rwx":rwx,"owner":owner,"group":group,"sid":sid,"filepath":filepath})
            # logger.info("Device:{} Query SUID Files Permissions Success. Result:{}".format(device_serial, results))
            return files
        
        except Exception as err:
            logger.exception("Device:{} Query SUID Files Permissions Fail! ADB Cmd Fail!".format(device_serial))
            return None

    #TODO 以特定用户账号权限启动特定的Activity
    def start_activity_with_user(self, device_serial:str, activity_name:str, user:str):
        logger.info("start_activity_with_user called! 功能尚未实现")
        return 1

    def install_apk(self, device_serial:str, apk_path:str):
        """
        安装APP 默认ROOT连接
        Return:
        暂不返回
        """
        con_dev = self.connect_dev(device_serial)
        if con_dev == None:
            raise_err( "Device {} Connect Fail!".format(device_serial))
        try:
            real_device_serial = self.__recheck_device_serial(device_serial)
            _, result = Bash_Script_Mgr.Instance().exec_cmd("adb -s {} install {}".format(real_device_serial,apk_path))
            if "success" in result.lower():
                logger.info("Install APK Finish:{}.".format(apk_path))
                return True
            else:
                return False
        except Exception as err:
            logger.exception("Device:{} Install APK Fail:{}.".format(device_serial, apk_path))
    
    def uninstall_apk(self, device_serial:str, pakcage_id:str):
        """
        卸载APK 默认ROOT连接
        Return:
        暂不返回
        """
        con_dev = self.connect_dev(device_serial, True)
        if con_dev == None:
            raise_err( "Device {} Connect Fail!".format(device_serial))
        
        try:
            adb.uninstall(pakcage_id)
            logger.info("Device:{} UnInstall Package Finish:{}.".format(device_serial, pakcage_id))

        except Exception as err:
            logger.exception("Device:{} UnInstall Package Fail:{}.".format(device_serial, pakcage_id))


    def query_android_selinux_status(self, device_serial:str):
        """
        查询Selinux启动状态  默认ROOT连接
        ADB_Mgr.Instance().query_android_selinux_status("a8d1de6f")
        Return:
        3种状态:
        Enforcing
        Permissive
        Disabled
        None: 设备之前没有连接成功或者其他失败     
        """
        con_dev = self.connect_dev(device_serial)
        if con_dev == None:
            raise_err( "Device {} Connect Fail!".format(device_serial))    

        try:
            selinux_status = adb.process(['getenforce']).recvall().decode('utf-8').strip()
            logger.info("Device:{} Query SeLinux Status Success. Status:{}".format(device_serial, selinux_status))
            if selinux_status == "Enforcing":
                return True
            else:
                return False
        except Exception as err:
            # 处理命令执行错误
            logger.exception("Device:{} Query SeLinux Status Fail! ADB Cmd Fail!".format(device_serial))
            return None
        

    def query_android_security_patch_status(self, device_serial:str):
        """
        检查android security patch日期  默认ROOT连接
        ADB_Mgr.Instance().query_android_security_patch_status("A2VCBB1C02004686")
        Return:
        None: 设备之前没有连接成功或者其他失败     
        """
        # getprop ro.build.version.security_patch
        con_dev = self.connect_dev(device_serial)
        if con_dev == None:
            raise_err( "Device {} Connect Fail!".format(device_serial))    

        try:
            security_patch = adb.process(['getprop','ro.build.version.security_patch']).recvall().decode('utf-8')
            logger.info("Device:{} Query Security Patch Status Success. Status:{}".format(device_serial, security_patch))
            #转换为日期

            return security_patch

        except Exception as err:
            # 处理命令执行错误
            logger.exception("Device:{} Query Security Patch Status Fail!".format(device_serial))
            return None
        

    def query_android_webview_version(self, device_serial:str):
        """
        检查android webview版本  默认ROOT连接
        ADB_Mgr.Instance().query_android_security_patch_status("a8d1de6f")
        Return:
        None: 设备之前没有连接成功或者其他失败     
        """
        #ADB_Mgr.Instance().query_android_webview_version("A2VCBB1C02004686")
        con_dev = self.connect_dev(device_serial)
        if con_dev == None:
            raise_err( "Device {} Connect Fail!".format(device_serial))    
        try:
            result1 = self.shell_cmd(device_serial, "dumpsys package com.android.webview | grep versionName", False)
            logger.info("Device:{} Query Package com.android.webview Finish. Result:{}".format(device_serial, result1))

            result2 = self.shell_cmd(device_serial, "dumpsys package com.google.android.webview | grep versionName", False)
            logger.info("Device:{} Query Package com.google.android.webview Finish. Result:{}".format(device_serial, result2))

            version = ""
            if result1 != "":
                version = result1
            else:
                version = result2
            
            if version == "":
                raise_err("未找到webview")
            return version
            # return "com.android.webview:{}\ncom.google.android.webview:{}".format(result1, result2)
            # return {"com.android.webview":result1,"com.google.android.webview":result2}
        
        except Exception as err:
            logger.exception("Device:{} Dumpsys Packages Fail!".format(device_serial))
            return None

    def list_debug_apps(self, device_serial:str,keylist:[]):
        """
        检查指定APP是否是疑似内部研发app  默认ROOT连接
        ADB_Mgr.Instance().list_debug_apps("c4f165f7")
        Return:
        ['','','']
        None: 设备之前没有连接成功或者其他失败     
        """
        con_dev = self.connect_dev(device_serial)
        if con_dev == None:
            raise_err( "Device {} Connect Fail!".format(device_serial))    
        
        #adb.process(['pm', 'list', 'packages', "grep | test"]).recvall().decode('utf-8')
        try:
            app_list = []
            for key in keylist:
                packages = self.shell_cmd(device_serial, "pm list packages | grep -i {}".format(key), False)
                for package_line in packages.splitlines():
                    packageitem = package_line.replace("package:", "")
                    if packageitem not in app_list:
                        app_list.append(packageitem)
                logger.info("Device:{} List Installed Test APPs Success. APPs:{}".format(device_serial, app_list))
            return app_list
        except Exception as err:
            logger.exception("Device:{} List Installed Test APPs Fail!".format(device_serial))
            return None




_instance = ADB_Mgr()
