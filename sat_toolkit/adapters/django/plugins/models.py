from __future__ import annotations

import importlib
import logging

from django.db import models

logger = logging.getLogger(__name__)


class Plugin(models.Model):
    name = models.CharField(max_length=255)
    description = models.CharField(max_length=512, blank=True)
    enabled = models.BooleanField(default=True)
    module_path = models.CharField(max_length=255, help_text="Python module path to the plugin class")
    license = models.CharField(max_length=255, blank=True)
    author = models.CharField(max_length=255, blank=True)
    parameters = models.TextField(blank=True)

    def __str__(self):
        return f"[Plugin:{self.pk} {self.name}]"

    # ---------- dynamic loading ----------
    def get_plugin_instance(self):
        module_name, class_name = self.module_path.rsplit(".", 1)
        module = importlib.import_module(module_name)
        plugin_class = getattr(module, class_name)
        return plugin_class()

    # ---------- execution (legacy) ----------
    def execute(self, target=None, parameters=None):
        """
        Legacy convenience wrapper.
        NOTE: execution logic should move to core/use-case layer; kept for backward compatibility.
        """
        if not self.enabled:
            return True
        plugin_instance = self.get_plugin_instance()
        result = plugin_instance.execute(target, parameters)
        return True if result is None else bool(result)

    @staticmethod
    def list_enabled():
        return list(Plugin.objects.filter(enabled=True))

    def detail(self):
        print(f"-- Plugin '{self}' Detail Info --")
        print(f"ID:\t{self.pk}")
        print(f"NAME:\t{self.name}")
        print(f"DESC:\t{self.description}")
        print(f"Enabled:\t{self.enabled}")
        print(f"License:\t{self.license}")
        print(f"Author:\t{self.author}")
        print(f"Parameters:\t{self.parameters}")
        print(f"++ Plugin '{self}' Detail Info Finish ++")


class PluginGroupTree(models.Model):
    parent = models.ForeignKey("PluginGroup", on_delete=models.CASCADE, related_name="parent")
    child = models.ForeignKey("PluginGroup", on_delete=models.CASCADE, related_name="child")

    sequence = models.SmallIntegerField(default=100)
    ignore_fail = models.BooleanField(default=False, help_text="Continue execution even if the child group fails")
    force_exec = models.BooleanField(default=False)

    class Meta:
        ordering = ["sequence"]

    def __str__(self):
        return (
            f"[Parent:{self.parent} Child:{self.child} "
            f"Seq:{self.sequence} IgnoreFail:{self.ignore_fail} "
            f"ForceExec:{self.force_exec}]"
        )


class PluginSequence(models.Model):
    plugingroup = models.ForeignKey("PluginGroup", on_delete=models.CASCADE)
    plugin = models.ForeignKey("Plugin", on_delete=models.CASCADE)
    sequence = models.SmallIntegerField(default=100)
    ignore_fail = models.BooleanField(default=False, help_text="Continue execution even if the plugin fails")

    class Meta:
        ordering = ["sequence"]

    def __str__(self):
        return f"[PluginSequence:{self.plugingroup} → {self.plugin} Seq:{self.sequence} IgnoreFail:{self.ignore_fail}]"


class PluginGroup(models.Model):
    name = models.CharField(max_length=255)
    description = models.CharField(max_length=512, blank=True)
    enabled = models.BooleanField(default=True)

    plugin_groups = models.ManyToManyField("self", through=PluginGroupTree, symmetrical=False)
    plugins = models.ManyToManyField(Plugin, through=PluginSequence, through_fields=("plugingroup", "plugin"))

    def plugins_count(self):
        return self.plugins.count()

    def plugin_groups_count(self):
        return self.plugin_groups.count()

    def child_plugin_groups(self):
        return PluginGroupTree.objects.filter(parent=self).order_by("sequence")

    def plugin_sequences(self):
        return PluginSequence.objects.filter(plugingroup=self).order_by("sequence")

    def __str__(self):
        return f"[PluginGroup:{self.pk} {self.name}]"

    @staticmethod
    def list_enabled():
        return list(PluginGroup.objects.filter(enabled=True))

    def detail(self):
        logger.info(f"-- PluginGroup '{self}' Detail Info --")
        logger.info(f"ID:\t{self.pk}")
        logger.info(f"NAME:\t{self.name}")
        logger.info(f"DESC:\t{self.description}")
        logger.info(f"Enabled:\t{self.enabled}")
        logger.info(f"PluginGroups List: Count:{self.plugin_groups_count()}")
        for tree in self.child_plugin_groups():
            logger.info(
                f"PluginGroup:{tree.child} Seq:{tree.sequence} IgnoreFail:{tree.ignore_fail} ForceExec:{tree.force_exec}"
            )
        logger.info(f"Plugins List: Count:{self.plugins_count()}")
        for seq in self.plugin_sequences():
            logger.info(f"Plugin:{seq.plugin} Seq:{seq.sequence} IgnoreFail:{seq.ignore_fail}")
        logger.info(f"++ PluginGroup '{self}' Detail Info Finish ++")

    # ---------- execution (legacy) ----------
    def execute(self, target=None, parameters=None, force_exec=True):
        """
        Legacy group executor (kept to avoid breaking callers).
        NOTE: orchestration belongs to core/use-case layer; this will be refactored later.
        """
        if not self.enabled and not force_exec:
            logger.info(f"PluginGroup {self} is disabled.")
            return True

        overall_ok = True

        for tree in self.child_plugin_groups():
            logger.info(f"Executing child PluginGroup: {tree.child}")
            ok = tree.child.execute(target, parameters, tree.force_exec)
            if not ok:
                logger.info(f"Child PluginGroup {tree.child} failed (ignore_fail={tree.ignore_fail})")
                if not tree.ignore_fail:
                    return False
                overall_ok = False

        for seq in self.plugin_sequences():
            logger.info(f"Executing Plugin: {seq.plugin}")
            from sat_toolkit.adapters.django.exploit_manager_factory import get_exploit_plugin_manager

            plugin_manager = get_exploit_plugin_manager()
            try:
                result = plugin_manager.execute_plugin(seq.plugin.name, target, parameters)
                if isinstance(result, dict):
                    if result.get("execution_type") == "async":
                        logger.warning(
                            f"Plugin {seq.plugin.name} started asynchronously. Group execution may not wait for completion."
                        )
                        ok = True
                    else:
                        ok = result.get("success", True)
                else:
                    ok = bool(result)
            except Exception as e:
                logger.error(f"Error executing plugin {seq.plugin.name}: {str(e)}")
                ok = False

            if not ok:
                logger.info(f"Plugin {seq.plugin} failed (ignore_fail={seq.ignore_fail})")
                if not seq.ignore_fail:
                    return False
                overall_ok = False

        return overall_ok


