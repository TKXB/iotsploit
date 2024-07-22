import logging
logger = logging.getLogger(__name__)


from django.db import models
from django.contrib import admin


class TestStepSequence(models.Model):
    testcase = models.ForeignKey("TestCase", on_delete=models.CASCADE)
    teststep = models.ForeignKey("TestStep", on_delete=models.CASCADE)
    sequence = models.SmallIntegerField(default=100)
    ignore_fail = models.BooleanField(default=False, help_text="Continue Execute Next TestStep Even If This Fail")
    

    def __str__(self):
        return "[TestStepSequence:{}:{}_{} Ignore_Fail:{}]".format(self.testcase.name, self.sequence, self.teststep.name, self.ignore_fail)


class TestStepSequence_Admin(admin.ModelAdmin):
    search_fields = list_display_links = list_display = ["id", "testcase", "teststep", "sequence", "ignore_fail"]

########################
class TestStepSequence_Inline(admin.TabularInline):
    model = TestStepSequence
    ordering = ["sequence"]