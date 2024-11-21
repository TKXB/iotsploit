# sat_toolkit/models/PluginGroupTree_Model.py

from django.db import models
from .PluginGroup_Model import PluginGroup

class PluginGroupTree(models.Model):
    parent = models.ForeignKey(PluginGroup, on_delete=models.CASCADE, related_name='parent')
    child = models.ForeignKey(PluginGroup, on_delete=models.CASCADE, related_name='child')
    force_exec = models.BooleanField(default=False)

    def __str__(self):
        return f"[Parent:{self.parent} Child:{self.child} Force Exec:{self.force_exec}]"