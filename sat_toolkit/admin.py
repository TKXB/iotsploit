from django.contrib import admin

# Register your models here.
# from .models.VehicleInfo_Model import VehicleInfo, VehicleInfo_Admin
# from .models.VehicleInfo_Model import VehicleModel, VehicleModel_Admin

# from .models.ClassifiedInfo_Model import VehiclePIN
# from .models.VehicleInfo_Model import VehiclePIN_Admin

# from .models.PassCondition_Model import PassCondition
# from .models.VehicleInfo_Model import PassCondition_Admin

# from models.WifiInfo import *



# admin.site.site_title = "Zeekr SAT Admin"

# admin.site.register(models.WifiInfo, models.WifiInfo_Admin)






admin.site.site_title = "SAT管理后台"
admin.site.site_header = "SAT管理后台"
# admin.site.register(VehicleInfo, VehicleInfo_Admin)
# admin.site.register(VehicleModel, VehicleModel_Admin)
# admin.site.register(VehiclePIN, VehiclePIN_Admin)
# admin.site.register(PassCondition, PassCondition_Admin)



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

from sat_toolkit.models.Plugin_Model import Plugin
from sat_toolkit.models.PluginGroup_Model import PluginGroup
from sat_toolkit.models.PluginGroupTree_Model import PluginGroupTree

class PluginAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "description", "enabled"]
    search_fields = ["name", "description"]

class PluginGroupTreeInline(admin.TabularInline):
    model = PluginGroupTree
    fk_name = 'parent'
    extra = 0

class PluginGroupAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "description", "plugins_count", "enabled"]
    search_fields = ["name", "description"]
    inlines = [PluginGroupTreeInline]
    filter_horizontal = ["plugins", "plugin_groups"]

admin.site.register(Plugin, PluginAdmin)
admin.site.register(PluginGroup, PluginGroupAdmin)