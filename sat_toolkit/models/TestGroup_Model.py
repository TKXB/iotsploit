import logging
logger = logging.getLogger(__name__)

from django.db import models
from django.contrib import admin

from sat_toolkit.tools.report_mgr import Report_Mgr
from sat_toolkit.tools.env_mgr import Env_Mgr

from .TestCase_Model import TestCase

class TestGroup(models.Model):
    name = models.CharField(max_length=255)
    description = models.CharField(max_length=512, blank=True)
    enabled = models.BooleanField(default=True, help_text="Enabled")

    test_groups = models.ManyToManyField("self", through="TestGroupTree", symmetrical=False)
    test_cases = models.ManyToManyField(TestCase)

    def test_groups_count(self):
        return "{}".format(self.test_groups.count())
    
    def test_cases_count(self):
        return "{}".format(self.test_cases.count())
    
    def child_test_count(self):
        return self.test_groups.count() + self.test_cases.count()
    
    def child_test_groups(self):
        return self.test_groups.through.objects.filter(parent = self)
    
    def __str__(self):
        return "[TestGroup:{} {}]".format(self.pk, self.name)
    
    @staticmethod
    def check_id_exist(ID):
        return TestGroup.objects.filter(pk=ID).exists()           

    @staticmethod
    def list_all():
        return list(TestGroup.objects.all())

    @staticmethod
    def list_enabled():
        return list(TestGroup.objects.filter(enabled=True))    


    # @staticmethod
    # def list_all():
    #     logger.info("TestGroups List Start")
    #     logger.info("ID\tNAME")
    #     for test_group in TestGroup.objects.all():
    #         logger.info("{}\t{}".format(test_group.pk, test_group.name))
    #     logger.info("TestGroups List Finish\n")

    def list_child_nodes(self, parent_list = [], prefix_str = "└"):
        parent_list.append(prefix_str + str(self))
        for group_tree in self.child_test_groups():
            parent_list.append("&emsp;" + prefix_str + str(group_tree.child))
            # group_tree.child.list_child_nodes(parent_list, " " + prefix_str)

        for test_case in self.test_cases.all():
            test_case.list_child_nodes(parent_list, "&emsp;" + prefix_str)
        
        return parent_list

    def detail(self):
        logger.info("-- TestGroup '{}' Detail Info --".format(self))
        logger.info("ID:\t{}".format(self.pk))
        logger.info("NAME:\t{}".format(self.name))
        logger.info("DESC:\t{}".format(self.description))
        logger.info("Enabled:\t{}".format(self.enabled))
        logger.info("TestGroups List: Count:{}".format(self.test_groups_count()))
        for group_tree in self.child_test_groups():
            logger.info("TestGroup:{} Force Exec:{}".format(group_tree.child, group_tree.force_exec))
        logger.info("TestCases List: Count:{}".format(self.test_cases_count()))
        for test_case in self.test_cases.all():
            logger.info("TestCase:{}".format(test_case))
        logger.info("++ TestGroup '{}' Detail Info Finish ++".format(self))            

    def exec(self, parent_record_dict:dict = {}, toc_level = 0, force_exec = True):
        test_result = 1
        test_result_desc = ""

        cached_result = Env_Mgr.Instance().query("test_result_cache_test_group_{}".format(str(self)))
        if cached_result == None or force_exec == True:
            logger.info("TestGroup:{} Not Execd Or Set Froce Exec. Contine Exec..".format(self))
        else:
            logger.info("TestGroup:{} Execd Before. SKIP Exec. Result:{} ".format(self, cached_result))
            test_result = cached_result["test_result"]
            test_result_desc = cached_result["test_result_desc"]
            return test_result, test_result_desc

        if self.enabled == True:
            if self.test_groups_count() != 0:
                self.detail()
                logger.info("TestGroup:{} Has Child TestGroups. Exec Child TestGroup First.".format(self))

                for group_tree in self.child_test_groups():
                    if Env_Mgr.Instance().get("SAT_AUDIT_STOP") == True:
                        logger.info("-- Rev STOP Cmd! Stop Exec --")
                        break

                    logger.info("Start To Exec Child TestGroup:{} Force Exec:{}".format(group_tree.child, group_tree.force_exec))
                    result, result_desc = group_tree.child.exec(parent_record_dict, toc_level, group_tree.force_exec)
                    logger.info("Child TestGroup Exec Finish. Result:{}. Continue Child TestGroup Exec -->>".format(result))
                    if result < 0:
                        test_result = result
                        test_result_desc = test_result_desc + "FAIL REASON:{} Exec Result:{}\n".format(group_tree.child, result)


            parent_record_dict["toc_level"] = toc_level
            parent_record_dict["test_group"] = self
            Report_Mgr.Instance().record_TestGroup_before_audit(parent_record_dict)
            logger.info("TestGroup Exec Start:{}".format(self))
            self.detail()

            for test_case in self.test_cases.all():
                if Env_Mgr.Instance().get("SAT_AUDIT_STOP") == True:
                    logger.info("-- Rev STOP Cmd! Stop Exec --")
                    break

                logger.info("Start To Exec TestCase:{} -->>".format(test_case))
                result, result_desc = test_case.exec(parent_record_dict, toc_level + 1)
                logger.info("TestCase Exec Finish. Result:{}. Continue TestCase Exec -->>".format(result))
                if result < 0:
                    test_result = result
                    test_result_desc = test_result_desc + "FAIL REASON:{} Exec Result:{}\n".format(test_case, result)

            if test_result < 0 :
                logger.info("TestGroup Exec Finish. Result:{} => Fail. FAIL REASON:\n{}".format(test_result, test_result_desc))
            else:
                logger.info("TestGroup Exec Finish. Result:{}.".format(test_result))
        else:
            test_result = 0
            test_result_desc = "Enabled Set False"
            logger.info("TestGroup Disabled. Result:{} REASON:{}".format(test_result, test_result_desc))

        
        parent_record_dict["test_result"] = test_result
        parent_record_dict["test_result_desc"] = test_result_desc
        Report_Mgr.Instance().record_TestGroup_after_audit(parent_record_dict)

        Env_Mgr.Instance().set("test_result_cache_test_group_{}".format(str(self)),
                                {
                                    "test_result":test_result,
                                    "test_result_desc":test_result_desc
                                }
                               )

        return test_result, test_result_desc




class TestGroupTree(models.Model):
    parent = models.ForeignKey(TestGroup, on_delete=models.CASCADE, related_name='parent')
    child = models.ForeignKey(TestGroup, on_delete=models.CASCADE, related_name='child')
    force_exec = models.BooleanField(default=False)

    def __str__(self):
        return "[Parent:{} Child:{} Force Exec:{}]".format(self.parent, self.child, self.force_exec)


########################
class TestCase_Inline(admin.TabularInline):
    model = TestGroup.test_cases.through

class TestGroup_Inline(admin.TabularInline):
    fk_name = 'parent'
    model = TestGroup.test_groups.through
    extra = 0

class TestGroup_Admin(admin.ModelAdmin):
    list_display_links = list_display = ["id", "name", "description", "child_test_count", "enabled"]    
    search_fields = ["name", "description"]

    exclude = ["test_cases","test_groups"]
    inlines = [TestGroup_Inline, TestCase_Inline]