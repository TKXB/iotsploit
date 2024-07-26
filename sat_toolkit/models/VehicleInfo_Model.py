import logging
logger = logging.getLogger(__name__)



from django.db import models
from django.contrib import admin

from .ClassifiedInfo_Model import VehiclePIN
from .PassCondition_Model import PassCondition

class VehicleModel(models.Model):
    Name = models.CharField(max_length=128)
    Description = models.CharField(max_length=512, blank=True)
    Pass_Condition = models.ForeignKey(PassCondition, related_name="Pass_Condition", null=True, blank=True, on_delete=models.SET_NULL)
    
    TCAM_AP_IP = models.CharField(max_length=255, blank=True)
    TCAM_SSH_USER   = models.CharField(max_length=255, blank=True)
    TCAM_SSH_PASSWD = models.CharField(max_length=255, blank=True)
    
    INTERNAL_IP_DICT = models.CharField(max_length=1024, blank=True)
    
    TCAM_ADB_PULL_FILE = models.CharField(max_length=255, blank=True)
    TCAM_ADB_PUSH_FILE = models.CharField(max_length=255, blank=True)
    TCAM_ADB_SHELL_PASSWD = models.CharField(max_length=255, blank=True)

    DHU_USB_VendorID = models.CharField(max_length=255, blank=True)
    DHU_USB_ProductID = models.CharField(max_length=255, blank=True)

    TCAM_USB_VendorID = models.CharField(max_length=255, blank=True)
    TCAM_USB_ProductID = models.CharField(max_length=255, blank=True)

    Attributes = models.TextField(blank=True)
    def __str__(self):
        return "[VehicleModel:{} {}]".format(self.pk, self.Name)

    def detail(self):
        logger.info("-- VehicleModel '{}' Detail Info --".format(self))
        logger.info("Name:\t{}".format(self.Name))
        logger.info("Description:\t{}".format(self.Description))
        logger.info("Pass_Condition:\t{}".format(self.Pass_Condition))
        logger.info("TCAM_AP_IP:\t{}".format(self.TCAM_AP_IP))
        logger.info("TCAM_SSH_USER:\t{}".format(self.TCAM_SSH_USER))
        logger.info("TCAM_SSH_PASSWD:\t{}".format(self.TCAM_SSH_PASSWD))
        logger.info("INTERNAL_IP_DICT:\t{}".format(self.INTERNAL_IP_DICT))
        logger.info("TCAM_ADB_PULL_FILE:\t{}".format(self.TCAM_ADB_PULL_FILE))
        logger.info("TCAM_ADB_PUSH_FILE:\t{}".format(self.TCAM_ADB_PUSH_FILE))
        logger.info("TCAM_ADB_SHELL_PASSWD:\t{}".format(self.TCAM_ADB_SHELL_PASSWD))

        logger.info("DHU_USB_VendorID:\t{}".format(self.DHU_USB_VendorID))
        logger.info("DHU_USB_ProductID:\t{}".format(self.DHU_USB_ProductID))

        logger.info("TCAM_USB_VendorID:\t{}".format(self.TCAM_USB_VendorID))
        logger.info("TCAM_USB_ProductID:\t{}".format(self.TCAM_USB_ProductID))

        logger.info("Attributes:\n{}".format(self.Attributes))



    def export_env(self):
        env_dict = {}

        if self.Pass_Condition != None:
            env_dict.update(self.Pass_Condition.export_env())
        
        env_dict["__SAT_ENV__VehicleModel_Name"] = self.Name
        env_dict["__SAT_ENV__VehicleModel_Description"] = self.Description      
        env_dict["__SAT_ENV__VehicleModel_TCAM_AP_IP"] = self.TCAM_AP_IP
        env_dict["__SAT_ENV__VehicleModel_TCAM_SSH_USER"] = self.TCAM_SSH_USER
        env_dict["__SAT_ENV__VehicleModel_TCAM_SSH_PASSWD"] = self.TCAM_SSH_PASSWD
        env_dict["__SAT_ENV__VehicleModel_INTERNAL_IP_DICT"] = self.INTERNAL_IP_DICT
        env_dict["__SAT_ENV__VehicleModel_TCAM_ADB_PULL_FILE"] = self.TCAM_ADB_PULL_FILE
        env_dict["__SAT_ENV__VehicleModel_TCAM_ADB_PUSH_FILE"] = self.TCAM_ADB_PUSH_FILE
        env_dict["__SAT_ENV__VehicleModel_TCAM_ADB_SHELL_PASSWD"] = self.TCAM_ADB_SHELL_PASSWD

        env_dict["__SAT_ENV__VehicleModel_DHU_USB_VendorID"] = self.DHU_USB_VendorID
        env_dict["__SAT_ENV__VehicleModel_DHU_USB_ProductID"] = self.DHU_USB_ProductID

        env_dict["__SAT_ENV__VehicleModel_TCAM_USB_VendorID"] = self.TCAM_USB_VendorID
        env_dict["__SAT_ENV__VehicleModel_TCAM_USB_ProductID"] = self.TCAM_USB_ProductID


        if self.Attributes != None:
            for attr in self.Attributes.splitlines():
                kv = attr.split("=",1)
                if len(kv) == 2:
                    env_dict["__SAT_ENV__VehicleModel_{}".format(kv[0])] = kv[1]
                else:
                    logger.error("Parse ENV From VehicleModel Attribute '{}' Fail".format(attr))
        return env_dict


########################

class VehicleInfo(models.Model):
    Description = models.CharField(max_length=255, blank=True)
    enabled = models.BooleanField(default=True, help_text="Enabled")

    Vehicle_Pin = models.ForeignKey(VehiclePIN, related_name="Vehicle_Pin", null=True, blank=True, on_delete=models.SET_NULL)

    TCAM_WIFI_SSID = models.CharField(max_length=32, blank=True)
    TCAM_WIFI_BSSID = models.CharField(max_length=32, blank=True)
    TCAM_WIFI_PASSWD = models.CharField(max_length=64, blank=True)

    DHU_WIFI_SSID = models.CharField(max_length=32, blank=True)
    DHU_WIFI_BSSID = models.CharField(max_length=32, blank=True)
    DHU_WIFI_PASSWD = models.CharField(max_length=64, blank=True)    

    TCAM_BLE_NAME = models.CharField(max_length=255, blank=True)
    TCAM_BLE_MAC = models.CharField(max_length=32, blank=True)
    
    DHU_ADB_SERIAL_ID = models.CharField(max_length=255, blank=True)
    DHU_ADB_NAME = models.CharField(max_length=255, blank=True)

    TCAM_ADB_SERIAL_ID = models.CharField(max_length=255, blank=True)
    TCAM_ADB_NAME = models.CharField(max_length=255, blank=True)

    vehicle_model = models.ForeignKey(VehicleModel, related_name="vehicle_model", null=True, blank=True, on_delete=models.SET_NULL)

    Attributes = models.TextField(blank=True)

    def __str__(self):
        return "[Vehicle:{} {}]".format(self.pk, self.Description)
    
    def save_wifi_info(self, TCAM_WIFI_SSID, TCAM_WIFI_BSSID, TCAM_WIFI_PASSWD, 
                            DHU_WIFI_SSID, DHU_WIFI_BSSID, DHU_WIFI_PASSWD):

        if TCAM_WIFI_SSID != None:
            self.TCAM_WIFI_SSID = TCAM_WIFI_SSID
            logger.info("UPDATE Vehicle WIFI INFO self.TCAM_WIFI_SSID:{}".format(self.TCAM_WIFI_SSID))

        if TCAM_WIFI_BSSID != None:
            self.TCAM_WIFI_BSSID = TCAM_WIFI_BSSID            
            logger.info("UPDATE Vehicle WIFI INFO self.TCAM_WIFI_BSSID:{}".format(self.TCAM_WIFI_BSSID))

        if TCAM_WIFI_PASSWD != None:
            self.TCAM_WIFI_PASSWD = TCAM_WIFI_PASSWD            
            logger.info("UPDATE Vehicle WIFI INFO self.TCAM_WIFI_PASSWD:{}".format(self.TCAM_WIFI_PASSWD))

        if DHU_WIFI_SSID != None:
            self.DHU_WIFI_SSID = DHU_WIFI_SSID            
            logger.info("UPDATE Vehicle WIFI INFO self.DHU_WIFI_SSID:{}".format(self.DHU_WIFI_SSID))

        if DHU_WIFI_BSSID != None:
            self.DHU_WIFI_BSSID = DHU_WIFI_BSSID  
            logger.info("UPDATE Vehicle WIFI INFO self.DHU_WIFI_BSSID:{}".format(self.DHU_WIFI_BSSID))

        if DHU_WIFI_PASSWD != None:
            self.DHU_WIFI_PASSWD = DHU_WIFI_PASSWD    
            logger.info("UPDATE Vehicle WIFI INFO self.DHU_WIFI_PASSWD:{}".format(self.DHU_WIFI_PASSWD))

        self.save()
        
    def export_env(self):
        env_dict = {}
        if self.vehicle_model != None:
            env_dict.update(self.vehicle_model.export_env())

        env_dict["__SAT_ENV__VehicleInfo_ID"] = str(self.pk)
        env_dict["__SAT_ENV__VehicleInfo_Description"] = self.Description

        if self.Vehicle_Pin != None:
            env_dict["__SAT_ENV__VehicleInfo_VIN"] = self.Vehicle_Pin.VIN
            env_dict["__SAT_ENV__VehicleInfo_DHU_PIN"] = self.Vehicle_Pin.DHU_PIN
            env_dict["__SAT_ENV__VehicleInfo_TCAM_PIN"] = self.Vehicle_Pin.TCAM_PIN

        env_dict["__SAT_ENV__VehicleInfo_TCAM_WIFI_SSID"] = self.TCAM_WIFI_SSID
        env_dict["__SAT_ENV__VehicleInfo_TCAM_WIFI_BSSID"] = self.TCAM_WIFI_BSSID
        env_dict["__SAT_ENV__VehicleInfo_TCAM_WIFI_PASSWD"] = self.TCAM_WIFI_PASSWD        

        env_dict["__SAT_ENV__VehicleInfo_DHU_WIFI_SSID"] = self.DHU_WIFI_SSID
        env_dict["__SAT_ENV__VehicleInfo_DHU_WIFI_BSSID"] = self.DHU_WIFI_BSSID
        env_dict["__SAT_ENV__VehicleInfo_DHU_WIFI_PASSWD"] = self.DHU_WIFI_PASSWD    

        env_dict["__SAT_ENV__VehicleInfo_TCAM_BLE_NAME"] = self.TCAM_BLE_NAME
        env_dict["__SAT_ENV__VehicleInfo_TCAM_BLE_MAC"] = self.TCAM_BLE_MAC

        env_dict["__SAT_ENV__VehicleInfo_DHU_ADB_SERIAL_ID"] = self.DHU_ADB_SERIAL_ID
        env_dict["__SAT_ENV__VehicleInfo_DHU_ADB_NAME"] = self.DHU_ADB_NAME

        env_dict["__SAT_ENV__VehicleInfo_TCAM_ADB_SERIAL_ID"] = self.TCAM_ADB_SERIAL_ID
        env_dict["__SAT_ENV__VehicleInfo_TCAM_ADB_NAME"] = self.TCAM_ADB_NAME

        if self.Attributes != None:
            for attr in self.Attributes.splitlines():
                kv = attr.split("=",1)
                if len(kv) == 2:
                    env_dict["__SAT_ENV__VehicleInfo_{}".format(kv[0])] = kv[1]
                else:
                    logger.error("Parse ENV From '{}' Fail".format(attr))
        
        # logger.debug("Vehicle ENV:{}".format(env_dict))
        return env_dict

    @staticmethod
    def check_id_exist(ID):
        return VehicleInfo.objects.filter(pk=ID).exists()
    
    @staticmethod
    def filter_vehicle_by_vin(VIN):
        return VehicleInfo.objects.filter(VIN=VIN)

    @staticmethod
    def list_all():
        return list(VehicleInfo.objects.all())
    
    @staticmethod
    def list_enabled():
        return list(VehicleInfo.objects.filter(enabled=True))       

    # @staticmethod
    # def dump_list():
    #     logger.info("Vehicles List Start")
    #     logger.info("ID\tDescription")
    #     for vehicle_info in VehicleInfo.objects.all():
    #         logger.info("{}\t{}".format(vehicle_info.pk, vehicle_info.Description))
    #     logger.info("Vehicles List Finish\n")

    @staticmethod
    def new_vehicle_fast(desc = "Test Vehicle"):
        vehicle_info = VehicleInfo(Description = desc)
        vehicle_info.save()
        logger.info("ADD New Vehicle:{}".format(vehicle_info))
        return vehicle_info

    def detail(self):
        logger.info("-- Vehicle '{}' Detail Info --".format(self))
        logger.info("ID:\t{}".format(self.pk))
        logger.info("Description:\t{}".format(self.Description))
        logger.info("Enabled:\t{}".format(self.enabled))

        if self.vehicle_model != None:
            logger.info("VehicleModel:\t{}".format(self.vehicle_model))
            self.vehicle_model.detail()
        else:
            logger.error("VehicleModel:{}".format("!!NOT SET!!"))

        if self.Vehicle_Pin != None:
            logger.info("Vehicle_Pin:\t{}".format(self.Vehicle_Pin))
            self.Vehicle_Pin.detail()
        else:
            logger.error("Vehicle_Pin:\t{}".format("!!NOT SET!!"))

        logger.info("TCAM_WIFI_SSID:\t{}".format(self.TCAM_WIFI_SSID))
        logger.info("TCAM_WIFI_BSSID:\t{}".format(self.TCAM_WIFI_BSSID))
        logger.info("TCAM_WIFI_PASSWD:\t{}".format(self.TCAM_WIFI_PASSWD))

        logger.info("DHU_WIFI_SSID:\t{}".format(self.DHU_WIFI_SSID))
        logger.info("DHU_WIFI_BSSID:\t{}".format(self.DHU_WIFI_BSSID))
        logger.info("DHU_WIFI_PASSWD:\t{}".format(self.DHU_WIFI_PASSWD))

        logger.info("TCAM_BLE_NAME:\t{}".format(self.TCAM_BLE_NAME))
        logger.info("TCAM_BLE_MAC:\t{}".format(self.TCAM_BLE_MAC))
        
        logger.info("DHU_ADB_SERIAL_ID:\t{}".format(self.DHU_ADB_SERIAL_ID))
        logger.info("DHU_ADB_NAME:\t{}".format(self.DHU_ADB_NAME))

        logger.info("TCAM_ADB_SERIAL_ID:\t{}".format(self.TCAM_ADB_SERIAL_ID))
        logger.info("TCAM_ADB_NAME:\t{}".format(self.TCAM_ADB_NAME))

        logger.info("Attributes:\n{}".format(self.Attributes))

        logger.info("++ Vehicle '{}' Detail Info Finish ++".format(self))


########################

class VehicleInfo_Admin(admin.ModelAdmin):
    list_display_links = list_display = ["id", "vehicle_model", "Description", "enabled"]
    search_fields = ["id", "Description",
                    "TCAM_WIFI_SSID", "TCAM_WIFI_BSSID", "TCAM_BLE_NAME", "TCAM_BLE_MAC", 
                    "DHU_ADB_SERIAL_ID", "DHU_ADB_NAME", "TCAM_ADB_SERIAL_ID", "TCAM_ADB_NAME", 
                    "Attributes"
                    ]
    

class VehicleModel_Inline(admin.TabularInline):
    model = VehicleModel
    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False


class VehicleInfo_Inline(admin.TabularInline):
    model = VehicleInfo
    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False
     
class VehicleModel_Admin(admin.ModelAdmin):
    list_display_links = list_display = ["id","Name","Description"]
    search_fields = ["id", "Name", "Description", "Attributes"]
    
    inlines = [VehicleInfo_Inline]

class VehiclePIN_Admin(admin.ModelAdmin):
    search_fields = list_display_links = list_display = ["VIN", "DHU_PIN", "TCAM_PIN", "DESC"]

    inlines = [VehicleInfo_Inline]

class PassCondition_Admin(admin.ModelAdmin):
    list_display_links = list_display = ["id","Name","Description"]
    search_fields = ["id", "Name", "Description", "Attributes"]
    
    inlines = [VehicleModel_Inline]
