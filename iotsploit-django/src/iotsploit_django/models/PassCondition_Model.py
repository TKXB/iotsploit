import logging
logger = logging.getLogger(__name__)

from django.db import models
from django.contrib import admin

class PassCondition(models.Model):
    Name = models.CharField(max_length=128)
    Description = models.CharField(max_length=512, blank=True)
    Attributes = models.TextField(blank=True)
    def __str__(self):
        return "[PassCondition:{} {}]".format(self.pk, self.Name)
    
    def export_env(self):
        env_dict = {}
        if self.Attributes != None:
            for attr in self.Attributes.splitlines():
                kv = attr.split("=",1)
                if len(kv) == 2:
                    env_dict["__SAT_ENV__PassCondition_{}".format(kv[0])] = kv[1]
                else:
                    logger.error("Parse ENV From PassCondition Attribute '{}' Fail".format(attr))
        return env_dict