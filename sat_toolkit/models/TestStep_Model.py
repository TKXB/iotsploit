import logging
logger = logging.getLogger(__name__)

from django.db import models
from django.contrib import admin

from sat_toolkit.tools.python_submodule_engine import Python_SubModule_Mgr
from sat_toolkit.tools.bash_script_engine import Bash_Script_Mgr
from sat_toolkit.tools.report_mgr import Report_Mgr
from sat_toolkit.tools.env_mgr import Env_Mgr

from .TestStepSequence_Model import TestStepSequence_Inline

class TestStep_Admin(admin.ModelAdmin):
    list_display_links = list_display = ["id", "name", "description", "enabled"]
    search_fields = ["id", "name", "description", "enabled", "cmd_type", "command_detail", "pass_condition", "predefined_list"]
    ordering = ["name", "id"] 
    inlines = [TestStepSequence_Inline]

class TestStep(models.Model):
    PASS_CONDITION_CHOICES = [
        ("Record", "Record  || Only Record Result. Always Pass."),
        ("WhiteMatch", "WhiteList || Check Result With Predefined List. Pass If Match"),
        ("BlackMatch", "BlackList || Check Result With Predefined List. Fail If Match"),
    ]

    CMD_TYPE_CHOICES = [
        ("Python File", "Python Submodule File"),
        ("Bash File", "Bash Script File"),
        ("Python Command", "Python Submodule Command"),
        ("Bash Command", "Bash Script Command"),        
    ]

    name = models.CharField(max_length=255)
    description = models.CharField(max_length=512, blank=True)
    enabled = models.BooleanField(default=True, help_text="Enabled")        
    cmd_type = models.CharField(max_length=32, choices=CMD_TYPE_CHOICES, default="Bash Command")
    command_detail = models.TextField(blank=True)
    pass_condition = models.CharField(max_length=32, choices=PASS_CONDITION_CHOICES, default="Record")
    predefined_list = models.TextField(blank=True)

    #0:record 1:whitelist 2:blacklist
    def pass_check(self):
        if self.pass_condition == TestStep.PASS_CONDITION_CHOICES[0][0]: #record
            return 0
        if self.pass_condition == TestStep.PASS_CONDITION_CHOICES[1][0]: #whitelist
            return 1
        if self.pass_condition == TestStep.PASS_CONDITION_CHOICES[2][0]: #blacklist
            return 2
        return 0

    def __str__(self):
        return "[TestStep:{} {}]".format(self.pk, self.name)
    
    @staticmethod
    def check_id_exist(ID):
        return TestStep.objects.filter(pk=ID).exists()   

    @staticmethod
    def list_all():
        return list(TestStep.objects.all())

    @staticmethod
    def list_enabled():
        return list(TestStep.objects.filter(enabled=True))       
    
    # @staticmethod
    # def list_all():
    #     logger.info("TestSteps List Start")
    #     logger.info("ID\tNAME")
    #     for test_step in TestStep.objects.all():
    #         logger.info("{}\t{}".format(test_step.pk, test_step.name))
    #     logger.info("TestSteps List Finish\n")
    
    def list_child_nodes(self, parent_list = [], prefix_str = "-"):
        if prefix_str[-1:] != "-":
            prefix_str = prefix_str[:-1] + "-"

        parent_list.append(prefix_str + str(self))    
        return parent_list

    def detail(self):
        logger.info("-- TestStep '{}' Detail Info --".format(self))
        logger.info("ID:\t{}".format(self.pk))
        logger.info("NAME:\t{}".format(self.name))
        logger.info("DESC:\t{}".format(self.description))
        logger.info("Enabled:\t{}".format(self.enabled))           
        logger.info("CMD Type:{}".format(self.cmd_type))
        logger.info("CMD Detail:\n{}".format(self.command_detail))
        logger.info("PassCondition:{}".format(self.pass_condition))
        logger.info("PredefinedList:\n{}".format(self.predefined_list))
        logger.info("++ TestStep '{}' Detail Info Finish ++".format(self))        

    def exec(self, parent_record_dict:dict = {}, toc_level = 0):
        Env_Mgr.Instance().set(Env_Mgr.ENV_PreFix + "TestResut_PNG", "")
        
        parent_record_dict["toc_level"] = toc_level
        parent_record_dict["test_step"] = self
        Report_Mgr.Instance().record_TestStep_before_audit(parent_record_dict)
        logger.info("TestStep Exec Start:{}".format(self))
        self.detail()
        if self.enabled == True:
            test_result = 1
            test_result_desc = ""        
            if self.cmd_type.startswith("Python"):
                test_result, test_result_desc, exec_log = Python_SubModule_Mgr.Instance().exec(self)
            if self.cmd_type.startswith("Bash"):
                test_result, test_result_desc, exec_log = Bash_Script_Mgr.Instance().exec(self)

            logger.info("TestStep Exec Finish. Result:{} REASON:{}".format(test_result, test_result_desc))

        else:
            test_result = 0
            test_result_desc = "Enabled Set False"   
            exec_log = test_result_desc
            logger.info("TestStep Disabled. Result:{} REASON:{}".format(test_result, test_result_desc))


        parent_record_dict["test_result"] = test_result
        parent_record_dict["test_result_desc"] = test_result_desc
        parent_record_dict["test_result_log"] = exec_log
        Report_Mgr.Instance().record_TestStep_after_audit(parent_record_dict)
        return test_result, test_result
