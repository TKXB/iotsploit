# sat_toolkit/models/PluginGroup_Model.py

from django.db import models
from .Plugin_Model import Plugin

class PluginGroup(models.Model):
    name = models.CharField(max_length=255)
    description = models.CharField(max_length=512, blank=True)
    enabled = models.BooleanField(default=True)

    # Many-to-Many relationship for nested groups
    plugin_groups = models.ManyToManyField("self", through="PluginGroupTree", symmetrical=False)
    # Many-to-Many relationship with plugins
    plugins = models.ManyToManyField(Plugin)

    def plugins_count(self):
        return f"{self.plugins.count()}"

    def plugin_groups_count(self):
        return f"{self.plugin_groups.count()}"

    def child_plugin_groups(self):
        return self.plugin_groups.through.objects.filter(parent=self)

    def __str__(self):
        return f"[PluginGroup:{self.pk} {self.name}]"

    @staticmethod
    def list_enabled():
        return list(PluginGroup.objects.filter(enabled=True))

    def detail(self):
        print(f"-- PluginGroup '{self}' Detail Info --")
        print(f"ID:\t{self.pk}")
        print(f"NAME:\t{self.name}")
        print(f"DESC:\t{self.description}")
        print(f"Enabled:\t{self.enabled}")
        print(f"PluginGroups List: Count:{self.plugin_groups_count()}")
        for group_tree in self.child_plugin_groups():
            print(f"PluginGroup:{group_tree.child} Force Exec:{group_tree.force_exec}")
        print(f"Plugins List: Count:{self.plugins_count()}")
        for plugin in self.plugins.all():
            print(f"Plugin:{plugin}")
        print(f"++ PluginGroup '{self}' Detail Info Finish ++")

    def execute(self, target=None, parameters=None, force_exec=True):
        if self.enabled:
            # Execute child plugin groups
            for group_tree in self.child_plugin_groups():
                print(f"Executing child PluginGroup: {group_tree.child}")
                group_tree.child.execute(target, parameters, group_tree.force_exec)

            # Execute plugins in this group
            for plugin in self.plugins.all():
                print(f"Executing Plugin: {plugin}")
                plugin.execute(target, parameters)
        else:
            print(f"PluginGroup {self.name} is disabled.")