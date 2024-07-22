import logging
logger = logging.getLogger(__name__)

from django.db import models
from django.contrib import admin

from sat_toolkit.tools.report_mgr import Report_Mgr
from sat_toolkit.tools.env_mgr import Env_Mgr

from .TestStep_Model import TestStep
from .TestStepSequence_Model import TestStepSequence_Inline
    
class TestCase_Admin(admin.ModelAdmin):
    list_display_links = list_display = ["id", "name", "description", "test_steps_count", "enabled"]    
    search_fields = ["name", "description"]

    exclude = ["test_steps"]
    inlines = [TestStepSequence_Inline]

class TestCase(models.Model):
    name = models.CharField(max_length=255)
    description = models.CharField(max_length=512, blank=True)    
    enabled = models.BooleanField(default=True, help_text="Enabled")    
    init_step = models.ForeignKey(TestStep, related_name="init_step", null=True, blank=True, on_delete=models.SET_NULL)
    cleanup_step = models.ForeignKey(TestStep, related_name="cleanup_step", null=True, blank=True, on_delete=models.SET_NULL)
    test_steps = models.ManyToManyField(TestStep, through="TestStepSequence")

    def init_step_exist(self):
        return self.init_step != None

    def cleanup_step_exist(self):
        return self.cleanup_step != None

    def test_steps_count(self):
        return "{}".format(self.test_steps.count())
    
    def test_steps_list(self):
        return self.test_steps.order_by("sequence")
    
    def test_steps_seqs(self):
        return self.test_steps.through.objects.filter(testcase = self).order_by("sequence")

    def __str__(self):
        return "[TestCase:{} {}]".format(self.pk, self.name)

    @staticmethod
    def check_id_exist(ID):
        return TestCase.filter(pk=ID).exists()

    @staticmethod
    def list_all():
        return list(TestCase.objects.all())
    
    @staticmethod
    def list_enabled():
        return list(TestCase.objects.filter(enabled=True))        

    # @staticmethod
    # def list_all():
    #     logger.info("TestCases List Start")
    #     logger.info("ID\tNAME")
    #     for test_case in TestCase.objects.all():
    #         logger.info("{}\t{}".format(test_case.pk, test_case.name))
    #     logger.info("TestCases List Finish\n")
    
    def list_child_nodes(self, parent_list = [], prefix_str = "└"):
        parent_list.append(prefix_str + str(self))
        if self.init_step != None:
            self.init_step.list_child_nodes(parent_list, "&emsp;" + prefix_str)

        for step_seq in self.test_steps_seqs():
            step_seq.teststep.list_child_nodes(parent_list, "&emsp;" + prefix_str)

        if self.cleanup_step != None:
            self.cleanup_step.list_child_nodes(parent_list, "&emsp;" + prefix_str)

        return parent_list

    def detail(self):
        logger.info("-- TestCase '{}' Detail Info --".format(self))
        logger.info("ID:\t{}".format(self.pk))
        logger.info("NAME:\t{}".format(self.name))
        logger.info("DESC:\t{}".format(self.description))
        logger.info("Enabled:\t{}".format(self.enabled))             
        logger.info("Init TestStep:    {}".format(self.init_step))
        logger.info("Cleanup TestStep: {}".format(self.cleanup_step))
        logger.info("TestStep List: Count:{}".format(self.test_steps_count()))
        for step_seq in self.test_steps_seqs():
            logger.info("  Sequence:{} \t TestStep:{} \t Ingore Fail:{}".format(step_seq.sequence, step_seq.teststep, step_seq.ignore_fail))
        
        logger.info("++ TestCase '{}' Detail Info Finish ++".format(self))

    def exec(self, parent_record_dict:dict = {}, toc_level = 0):
        parent_record_dict["toc_level"] = toc_level      
        parent_record_dict["test_case"] = self
        Report_Mgr.Instance().record_TestCase_before_audit(parent_record_dict)
        logger.info("TestCase Exec Start:{}".format(self))
        self.detail()
        
        if self.enabled == True:
            test_result = 1
            test_result_desc = ""
    
            if self.init_step != None:
                if Env_Mgr.Instance().get("SAT_AUDIT_STOP") == True:
                    logger.info("-- Rev STOP Cmd! Stop Exec --")
                else:
                    logger.info("Init TestStep SET. Start To Exec Init TestStep {} -->>".format(self.init_step))
                    result, result_desc = self.init_step.exec(parent_record_dict, toc_level + 1)
                    if result < 0 :
                        logger.info("Init TestStep SET. TestStep Exec Finish. Result:{} => Fail. REASON:{}. Abort TestCase Exec.".format(result, result_desc))

                        test_result = result
                        test_result_desc = test_result_desc + "FAIL REASON:{} Exec Result:{}\n".format(self.init_step, result)
                        parent_record_dict["test_result"] = test_result
                        parent_record_dict["test_result_desc"] = test_result_desc
                        Report_Mgr.Instance().record_TestCase_after_audit(parent_record_dict)
                        return test_result, test_result
                    else:
                        logger.info("Init TestStep SET. TestStep Exec Finish. Result:{}. Continue TestCase Exec -->>".format(result))
            else:
                logger.info("Init TestStep Not SET. Skip -->>")


            for step_seq in self.test_steps_seqs():
                if Env_Mgr.Instance().get("SAT_AUDIT_STOP") == True:
                    logger.info("-- Rev STOP Cmd! Stop Exec --")
                    break

                logger.info("Start To Exec: {} -->>".format(step_seq))
                result, result_desc = step_seq.teststep.exec(parent_record_dict, toc_level + 1)
                if result < 0 :
                    test_result = result
                    test_result_desc = test_result_desc + "FAIL REASON:{} Exec Result:{}\n".format(step_seq.teststep, result)

                    if step_seq.ignore_fail == True:
                        logger.info("TestStep Exec Finish. Result:{} => Fail. REASON:{}. Ignore Fail && Continue Next TestCase Exec -->>".format(result, result_desc))
                    else:
                        logger.info("TestStep Exec Finish. Result:{} => Fail. REASON:{}. Ignore Fail Is Fail && Abort TestCase Exec.".format(result, result_desc))
                        test_result_desc = test_result_desc + "FAIL REASON:Ignore Fail Is Fail && Abort TestCase Exec. \n"
                        break
                else:
                    logger.info("TestStep Exec Finish. Result:{}. Continue TestCase Exec -->>".format(result))

            if self.cleanup_step != None:
                if Env_Mgr.Instance().get("SAT_AUDIT_STOP") == True:
                    logger.info("-- Rev STOP Cmd! Stop Exec --")
                else:
                    logger.info("CleanUp TestStep SET. Start To Exec CleanUp TestStep {} -->>".format(self.cleanup_step))
                    result, result_desc = self.cleanup_step.exec(parent_record_dict, toc_level + 1)
                    if result < 0 :
                        logger.info("CleanUp TestStep SET. TestStep Exec Finish. Result:{} => Fail.REASON:{}".format(result, result_desc))
                        test_result = result
                        test_result_desc = test_result_desc + "FAIL REASON:{} Exec Result:{}\n".format(self.cleanup_step, result)
                    else:
                        logger.info("CleanUp TestStep SET. TestStep Exec Finish. Result:{}. Set ExecResult:{}".format(result, test_result))
            else:
                logger.info("CleanUp TestStep Not SET. Set ExecResult:{}".format(test_result))

        else:
            test_result = 0
            test_result_desc = "Enabled Set False"        
            logger.info("TestCase Disabled. Result:{} REASON:{}".format(test_result, test_result_desc))


        parent_record_dict["test_result"] = test_result
        parent_record_dict["test_result_desc"] = test_result_desc
        Report_Mgr.Instance().record_TestCase_after_audit(parent_record_dict)
        return test_result, test_result

