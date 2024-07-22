import logging
logger = logging.getLogger(__name__)

from django.db import models
from django.contrib import admin

from sat_toolkit.tools.report_mgr import Report_Mgr
from sat_toolkit.tools.env_mgr import Env_Mgr

from .TestGroup_Model import TestGroup


class TestStands(models.Model):
    name = models.CharField(max_length=255)
    description = models.CharField(max_length=512, blank=True)    
    enabled = models.BooleanField(default=True, help_text="Enabled")
    test_groups = models.ManyToManyField(TestGroup)

    def test_groups_count(self):
        return "{}".format(self.test_groups.count())
    
    def __str__(self):
        return "[TestStands:{} {}]".format(self.pk, self.name)
    
    @staticmethod
    def check_id_exist(ID):
        return TestStands.objects.filter(pk=ID).exists()        

    @staticmethod
    def list_all():
        return list(TestStands.objects.all())
    
    @staticmethod
    def list_enabled():
        return list(TestStands.objects.filter(enabled=True))    

    def list_child_nodes(self, parent_list = [], prefix_str = "└"):
        parent_list.append(prefix_str + str(self))
        for test_group in self.test_groups.all():
            test_group.list_child_nodes(parent_list, "&emsp;" + prefix_str)
        
        return parent_list

    def detail(self):
        logger.info("-- TestStands '{}' Detail Info --".format(self))
        logger.info("ID:\t{}".format(self.pk))
        logger.info("NAME:\t{}".format(self.name))
        logger.info("DESC:\t{}".format(self.description))        
        logger.info("Enabled:\t{}".format(self.enabled))              
        logger.info("TestGroups List: Count:{}".format(self.test_groups_count()))
        for test_group in self.test_groups.all():
            logger.info("TestGroup:{}".format(test_group))
        logger.info("++ TestStands '{}' Detail Info Finish ++".format(self))

    def exec(self, parent_record_dict:dict = {}, toc_level = 0):
        parent_record_dict["toc_level"] = toc_level        
        parent_record_dict["test_stand"] = self        
        Report_Mgr.Instance().record_TestStand_before_audit(parent_record_dict)
        logger.info("TestStand Exec Start:{}".format(self))
        self.detail()
        
        if self.enabled == True:
            test_result = 1
            test_result_desc = ""
            for test_group in self.test_groups.all():
                if Env_Mgr.Instance().get("SAT_AUDIT_STOP") == True:
                    logger.info("-- Rev STOP Cmd! Stop Exec --")
                    break

                logger.info("Start To Exec TestGroup:{} -->>".format(test_group))
                result, result_desc = test_group.exec(parent_record_dict, toc_level + 1)
                logger.info("TestGroup Exec Finish. Result:{}. REASON:{} TestGroup Exec Continue-->>".format(result, result_desc))
                if result < 0:
                    test_result = result
                    test_result_desc = test_result_desc + "FAIL REASON:{} Exec Result:{}\n".format(test_group, result)

            if test_result < 0 :
                logger.info("TestStand Exec Finish. Result:{} => Fail. FAIL REASON:\n{}".format(test_result, test_result_desc))
            else:
                logger.info("TestStand Exec Finish. Result:{}.".format(test_result))
        else:
            test_result = 0
            test_result_desc = "Enabled Set False"
            logger.info("TestStand Disabled. Result:{} REASON:{}".format(test_result, test_result_desc))


        parent_record_dict["test_result"] = test_result
        parent_record_dict["test_result_desc"] = test_result_desc
        Report_Mgr.Instance().record_TestStand_after_audit(parent_record_dict)

        return test_result, test_result_desc



########################
class TestStands_Inline(admin.TabularInline):
    model = TestStands.test_groups.through

class TestStands_Admin(admin.ModelAdmin):
    list_display_links = list_display = ["id", "name", "description", "test_groups_count", "enabled"]
    search_fields = ["name", "description"]

    exclude = ["test_groups"]
    inlines = [TestStands_Inline]