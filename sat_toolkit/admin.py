from django.contrib import admin

# Register your models here.
from .models.TestCase_Model import TestCase, TestCase_Admin 
from .models.TestGroup_Model import TestGroup, TestGroup_Admin
from .models.TestStands_Model import TestStands, TestStands_Admin
from .models.TestStep_Model import TestStep, TestStep_Admin 
from .models.TestStepSequence_Model import TestStepSequence, TestStepSequence_Admin 


# from .models.TestStepSequence import *
from .models.VehicleInfo_Model import VehicleInfo, VehicleInfo_Admin
from .models.VehicleInfo_Model import VehicleModel, VehicleModel_Admin

from .models.ClassifiedInfo_Model import VehiclePIN
from .models.VehicleInfo_Model import VehiclePIN_Admin

from .models.PassCondition_Model import PassCondition
from .models.VehicleInfo_Model import PassCondition_Admin

# from models.WifiInfo import *



# admin.site.site_title = "Zeekr SAT Admin"

# admin.site.register(models.WifiInfo, models.WifiInfo_Admin)






admin.site.site_title = "SAT管理后台"
admin.site.site_header = "SAT管理后台"
admin.site.register(TestStep, TestStep_Admin)
admin.site.register(TestCase, TestCase_Admin)
admin.site.register(TestStepSequence, TestStepSequence_Admin)
admin.site.register(TestGroup, TestGroup_Admin)
admin.site.register(TestStands, TestStands_Admin)
admin.site.register(VehicleInfo, VehicleInfo_Admin)
admin.site.register(VehicleModel, VehicleModel_Admin)
admin.site.register(VehiclePIN, VehiclePIN_Admin)
admin.site.register(PassCondition, PassCondition_Admin)



from .models.DoIP_Diagnostic_Database_Model import *
doip_diag_admin = admin.AdminSite("DoIP_Diag_Admin")
doip_diag_admin.site_title = "DoIP诊断数据库"
doip_diag_admin.site_header = "DoIP诊断数据库"

admin.site.register(NegativeResponseCode, NegativeResponseCode_Admin)
admin.site.register(ECU, ECU_Admin)
admin.site.register(SW, SW_Admin)
admin.site.register(Service, Service_Admin)
admin.site.register(DataParameter, DataParameter_Admin)
admin.site.register(DataIdentifier, DataIdentifier_Admin)
admin.site.register(Subfunction, Subfunction_Admin)
admin.site.register(RoutineIdentifier, RoutineIdentifier_Admin)
admin.site.register(ResponseItem, ResponseItem_Admin)