import logging
logger = logging.getLogger(__name__)

from django.db import models
from django.contrib import admin

class VehiclePIN(models.Model):
    VIN = models.CharField(max_length=128, unique=True)
    DHU_PIN = models.CharField(max_length=128, blank=True)
    TCAM_PIN = models.CharField(max_length=128, blank=True)
    DESC = models.CharField(max_length=512, blank=True)

    def __str__(self):
        return "[VehiclePIN:{} {} {}]".format(self.pk, self.VIN, self.DESC)

    def check_effect(self):
        if self.VIN != None and self.DHU_PIN != None and self.TCAM_PIN != None :
            return True
        else:
            return False
        
    def detail(self):
        logger.info("-- VehiclePIN '{}' Detail Info --".format(self))
        logger.info("VIN:\t{}".format(self.VIN))
        logger.info("DHU_PIN:\t{}".format(self.DHU_PIN))
        logger.info("TCAM_PIN:\t{}".format(self.TCAM_PIN))
        logger.info("DESC:\t{}".format(self.DESC))
        logger.info("++ VehiclePIN '{}' Detail Info Finish ++".format(self))

########################