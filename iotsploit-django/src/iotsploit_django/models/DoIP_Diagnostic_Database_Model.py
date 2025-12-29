import logging
logger = logging.getLogger(__name__)

from django.db import models
from django.contrib import admin

import xml.etree.ElementTree as ET

def Parse_DSA_XML(xml_path:str):
    logger.info("Start To Parse XML File:{}".format(xml_path))
    root_xml_tree = ET.parse(xml_path)
    project_node = root_xml_tree.getroot()
    system_node = project_node.find("System")
    NegativeResponseCode.parse_from_NegativeResponseCodes_In_Root(system_node)
    ECU.parse_from_ECUs(system_node)

    logger.info("Parse XML File:{} Finish.".format(xml_path))


class NegativeResponseCode(models.Model):
    Name = models.CharField(max_length=255)
    Code = models.CharField(max_length=16)

    def __str__(self):
        return "[NegativeResponseCode:{} {}]".format(self.Name, self.Code)

    @staticmethod
    def parse_from_NegativeResponseCodes_In_Root(et:ET):
        logger.info("Find NegativeResponseCode In Root Start -->>")        
        for ele in et.find("NegativeResponseCodes").findall("NegativeResponseCode"):
            logger.info("Find NegativeResponseCode:{}".format(ele.attrib))
            
            db_item = NegativeResponseCode()
            db_item.Name = ele.get("Name")
            db_item.Code = ele.get("Code")
            db_item.save()

        logger.info("Find NegativeResponseCode In Root Finish -->>")


class ECU(models.Model):
    Name = models.CharField(max_length=255)
    address = models.CharField(max_length=16)
    IsBootloader = models.BooleanField()

    def __str__(self):
        return "[ECU:{} {}]".format(self.Name, self.address)

    @staticmethod
    def parse_from_ECUs(et):
        logger.info("Find ECU Start -->>")        
        for ele in et.find("ECUs").findall("ECU"):
            logger.info("Find ECU:{}".format(ele.attrib))
            db_item = ECU()
            db_item.Name = ele.get("Name")
            db_item.address = ele.get("address")
            db_item.IsBootloader = ele.get("IsBootloader")
            db_item.save()
            SW.parse_from_SWs(db_item, ele)

        logger.info("Find ECU Finish -->>")


class SW(models.Model):
    Name = models.CharField(max_length=255)
    DiagnosticPartNumber = models.CharField(max_length=255)
    Type = models.CharField(max_length=32)
    bind_ECU = models.ForeignKey(ECU, on_delete=models.CASCADE)

    def __str__(self):
        return "[SW:{} @ ECU:{}]".format(self.Name, self.bind_ECU.Name)    

    @staticmethod
    def parse_from_SWs(bind_ECU:ECU, et):
        logger.info("Find SW Start Bind_ECU:{} -->>".format(bind_ECU))        
        for ele in et.find("SWs").findall("SW"):
            logger.info("Find ECU:{}".format(ele.attrib))        
            db_item = SW()
            db_item.Name = ele.get("Name")
            db_item.DiagnosticPartNumber = ele.get("DiagnosticPartNumber")
            db_item.Type = ele.get("Type")
            db_item.bind_ECU = bind_ECU
            db_item.save()

            Service.parse_from_Services(db_item, ele)

        logger.info("Find SW Finish -->>")    


class Service(models.Model):
    Name = models.CharField(max_length=255)
    Service_ID = models.CharField(max_length=16)
    bind_SW = models.ForeignKey(SW,on_delete=models.CASCADE) 

    def __str__(self):
        return "[Service:{} @ SW:{}]".format(self.Name, self.bind_SW.Name)    

    @staticmethod
    def parse_from_Services(bind_SW:SW, et):
        logger.info("Find Service Start Bind_SW:{} -->>".format(bind_SW))        
        for ele in et.find("Services").findall("Service"):
            logger.info("Find Service:{}".format(ele.attrib))        
            db_item = Service()
            db_item.Name = ele.get("Name")
            db_item.Service_ID = ele.get("ID")
            db_item.bind_SW = bind_SW

            db_item.save()

            Subfunction.parse_from_Subfunctions(db_item, ele)
            DataIdentifier.parse_from_DataIdentifiers(db_item, ele)
            DataParameter.parse_from_DataParameters_IN_Service(db_item, ele)


        logger.info("Find Service Finish -->>")    


class DataParameter(models.Model):
    Name = models.CharField(max_length=255)
    DataParameter_ID = models.CharField(max_length=16)
    Size = models.SmallIntegerField()
    bind_Service = models.ForeignKey(Service, on_delete=models.CASCADE) 

    @staticmethod
    def parse_from_DataParameters_IN_Service(bind_SW:SW, et):
        if et.find("DataParameters") == None:
            return

        logger.info("Find DataParameter Start Bind_SW:{} -->>".format(bind_SW))        
        for ele in et.find("DataParameters").findall("DataParameter"):
            logger.info("Find DataParameter:{}".format(ele.attrib))        
            db_item = DataParameter()
            db_item.Name = ele.get("Name")
            db_item.DataParameter_ID = ele.get("ID")
            db_item.Size = ele.get("Size")
            db_item.bind_Service = bind_SW
            db_item.save()

        logger.info("Find Service Finish -->>")    


class DataIdentifier(models.Model):
    Name = models.CharField(max_length=255)
    DataIdentifier_ID = models.CharField(max_length=16)
    Size = models.SmallIntegerField()
    bind_Service = models.ForeignKey(Service, on_delete=models.CASCADE) 

    @staticmethod
    def parse_from_DataIdentifiers(bind_Service:SW, et):
        if et.find("DataIdentifiers") == None:
            # logger.info("{} Not Have DataIdentifier".format(bind_Service))
            return

        logger.info("Find DataIdentifier Start Bind_Service:{} -->>".format(bind_Service))        
        for ele in et.find("DataIdentifiers").findall("DataIdentifier"):
            logger.info("Find DataIdentifier:{}".format(ele.attrib))        
            db_item = DataIdentifier()
            db_item.Name = ele.get("Name")
            db_item.DataIdentifier_ID = ele.get("ID")
            db_item.Size = ele.get("Size")            
            db_item.bind_Service = bind_Service

            db_item.save()
            ResponseItem.parse_from_ResponseItems_In_DataIdentifier(db_item, ele)
            
        logger.info("Find DataIdentifier Finish -->>")    


class Subfunction(models.Model):
    Name = models.CharField(max_length=255)
    Subfunction_ID = models.CharField(max_length=16)
    bind_Service = models.ForeignKey(Service, on_delete=models.CASCADE) 

    def __str__(self):
        return "[Subfunction:{} @ Service:{}]".format(self.Name, self.bind_Service.Name)    

    @staticmethod
    def parse_from_Subfunctions(bind_Service:SW, et):
        if et.find("Subfunctions") == None:
            logger.info("{} Not Have SubFunctions".format(bind_Service))
            return

        logger.info("Find SubFunction Start Bind_Service:{} -->>".format(bind_Service))        
        for ele in et.find("Subfunctions").findall("Subfunction"):
            logger.info("Find Subfunction:{}".format(ele.attrib))        
            db_item = Subfunction()
            db_item.Name = ele.get("Name")
            db_item.Subfunction_ID = ele.get("ID")
            db_item.bind_Service = bind_Service

            db_item.save()
            ResponseItem.parse_from_ResponseItems_In_SubFunction(db_item, ele)
            RoutineIdentifier.parse_from_RoutineIdentifiers_In_SubFunction(db_item, ele)

        logger.info("Find SubFunction Finish -->>")    


class RoutineIdentifier(models.Model):
    Name = models.CharField(max_length=255)
    RoutineIdentifier_ID = models.CharField(max_length=16, blank=True)
    RoutineType = models.CharField(max_length=16, blank=True)
    ExecutionTime = models.CharField(max_length=16, blank=True)
    RequestLength = models.CharField(max_length=16, blank=True)
    ResponseLength = models.CharField(max_length=16, blank=True)

    bind_Subfunction = models.ForeignKey(Subfunction, on_delete=models.CASCADE) 

    @staticmethod
    def parse_from_RoutineIdentifiers_In_SubFunction(bind_SubFuction:Subfunction, et):
        if et.find("RoutineIdentifiers") == None:
            # logger.info("{} Not Have ResponseItems".format(bind_SubFuction))
            return
        
        logger.info("Find RoutineIdentifier Start bind_SubFuction:{} -->>".format(bind_SubFuction))        
        for ele in et.find("RoutineIdentifiers").findall("RoutineIdentifier"):
            logger.info("Find RoutineIdentifier:{}".format(ele.attrib))        
            db_item = RoutineIdentifier()
            db_item.Name = ele.get("Name")
            db_item.RoutineIdentifier_ID = ele.get("ID")
            db_item.RoutineType = ele.get("RoutineType")
            db_item.ExecutionTime = ele.get("ExecutionTime")
            db_item.RequestLength = ele.get("RequestLength")            
            db_item.ResponseLength = ele.get("ResponseLength")
            db_item.bind_Subfunction = bind_SubFuction

            db_item.save()

            ResponseItem.parse_from_ResponseItems_In_RoutineIdentifier(db_item, ele)

        logger.info("Find RoutineIdentifier Finish -->>")    


class ResponseItem(models.Model):
    Name = models.CharField(max_length=255)
    InDataType = models.CharField(max_length=16)
    OutDataType = models.CharField(max_length=16) 
    Offset = models.CharField(max_length=16) 
    Size = models.CharField(max_length=16) 
    ResultPrecision = models.CharField(max_length=16) 
    Inner_ID = models.CharField(max_length=16) 
    Formula = models.CharField(max_length=64) 
    Unit = models.CharField(max_length=64) 
    CompareValue = models.CharField(max_length=64) 

    bind_Subfunction = models.ForeignKey(Subfunction, on_delete=models.CASCADE, null=True, blank=True) 
    bind_DataIdentifier = models.ForeignKey(DataIdentifier, on_delete=models.CASCADE, null=True, blank=True) 
    bind_RoutineIdentifier = models.ForeignKey(RoutineIdentifier, on_delete=models.CASCADE, null=True, blank=True) 


    def __str__(self):
        return "[ResponseItem:{}]".format(self.Name)    

    @staticmethod
    def __parse_from_ele(db_item, ele):
        db_item.Name = ele.get("Name")
        db_item.InDataType = ele.get("InDataType")
        db_item.OutDataType = ele.get("OutDataType")
        db_item.Offset = ele.get("Offset")
        db_item.Size = ele.get("Size")
        db_item.ResultPrecision = ele.get("ResultPrecision")
        if ele.find("Inner_ID") != None:
            db_item.Inner_ID = ele.find("Inner_ID").text
        if ele.find("Formula") != None:
            db_item.Formula = ele.find("Formula").text          
        if ele.find("Unit") != None:
            db_item.Unit = ele.find("Unit").text
        if ele.find("CompareValue") != None:
            db_item.CompareValue = ele.find("CompareValue").text  


    @staticmethod
    def parse_from_ResponseItems_In_SubFunction(bind_SubFuction:Subfunction, et):
        if et.find("ResponseItems") == None:
            return
        
        logger.info("Find ResponseItem Start bind_SubFuction:{} -->>".format(bind_SubFuction))        
        for ele in et.find("ResponseItems").findall("ResponseItem"):
            logger.info("Find ResponseItem:{}".format(ele.attrib))        
            db_item = ResponseItem()
            ResponseItem.__parse_from_ele(db_item, ele)
            db_item.bind_Subfunction = bind_SubFuction
            db_item.save()

        logger.info("Find ResponseItem Finish -->>")   


    @staticmethod
    def parse_from_ResponseItems_In_DataIdentifier(bind_DataIdentifier:DataIdentifier, et):
        if et.find("ResponseItems") == None:
            return
        
        logger.info("Find ResponseItem Start bind_DataIdentifier:{} -->>".format(bind_DataIdentifier))        
        for ele in et.find("ResponseItems").findall("ResponseItem"):
            logger.info("Find ResponseItem:{}".format(ele.attrib))        
            db_item = ResponseItem()
            ResponseItem.__parse_from_ele(db_item, ele)
            db_item.bind_DataIdentifier = bind_DataIdentifier
            db_item.save()

        logger.info("Find ResponseItem Finish -->>")    

    @staticmethod
    def parse_from_ResponseItems_In_RoutineIdentifier(bind_RoutineIdentifier:RoutineIdentifier, et):
        if et.find("ResponseItems") == None:
            return
        
        logger.info("Find ResponseItem Start bind_RoutineIdentifier:{} -->>".format(bind_RoutineIdentifier))        
        for ele in et.find("ResponseItems").findall("ResponseItem"):
            logger.info("Find ResponseItem:{}".format(ele.attrib))        
            db_item = ResponseItem()
            ResponseItem.__parse_from_ele(db_item, ele)
            db_item.bind_RoutineIdentifier = bind_RoutineIdentifier
            db_item.save()

        logger.info("Find ResponseItem Finish -->>")    


class ResponseItem_Inline(admin.TabularInline):
    model = ResponseItem
    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False  

class Subfunction_Inline(admin.TabularInline):
    model = Subfunction
    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False    
    
class SW_Inline(admin.TabularInline):
    model = SW
    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False    
    
class Service_Inline(admin.TabularInline):
    model = Service
    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False        

class DataParameter_Inline(admin.TabularInline):
    model = DataParameter
    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False     

class DataIdentifier_Inline(admin.TabularInline):
    model = DataIdentifier
    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False     


class RoutineIdentifier_Inline(admin.TabularInline):
    model = RoutineIdentifier
    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False   


####################################

class NegativeResponseCode_Admin(admin.ModelAdmin):
    list_display_links = list_display = search_fields = ["id", "Name", "Code"]        


class ECU_Admin(admin.ModelAdmin):
    list_display_links = list_display = search_fields = ["id", "Name", "address", "IsBootloader"]
    inlines = [SW_Inline]

class SW_Admin(admin.ModelAdmin):
    list_display_links = list_display = search_fields = ["id", "Name", "DiagnosticPartNumber", "Type", "bind_ECU"]
    inlines = [Service_Inline]    

class Service_Admin(admin.ModelAdmin):
    list_display_links = list_display = search_fields = ["id", "Name", "Service_ID", "bind_SW"]
    inlines = [Subfunction_Inline, DataIdentifier_Inline, DataParameter_Inline]    

class DataParameter_Admin(admin.ModelAdmin):
    list_display_links = list_display = search_fields = ["id", "Name", "DataParameter_ID", "Size", "bind_Service"]

class DataIdentifier_Admin(admin.ModelAdmin):
    list_display_links = list_display = search_fields = ["id", "Name", "DataIdentifier_ID", "Size", "bind_Service"]
    inlines = [ResponseItem_Inline]   

class Subfunction_Admin(admin.ModelAdmin):
    list_display_links = list_display = search_fields = ["id", "Name", "Subfunction_ID", "bind_Service"]
    inlines = [ResponseItem_Inline, RoutineIdentifier_Inline]

class RoutineIdentifier_Admin(admin.ModelAdmin):
    list_display_links = list_display = search_fields = ["id", "Name", "RoutineIdentifier_ID", "RoutineType", "ExecutionTime", "RequestLength", "ResponseLength", "bind_Subfunction"]
    inlines = [ResponseItem_Inline]   

class ResponseItem_Admin(admin.ModelAdmin):
    list_display_links = list_display = search_fields = \
        ["id", "Name", "InDataType", "OutDataType", "Offset", "Size", "ResultPrecision", "Inner_ID", "Formula", "Unit", "CompareValue", "bind_Subfunction", "bind_DataIdentifier", "bind_RoutineIdentifier"]
