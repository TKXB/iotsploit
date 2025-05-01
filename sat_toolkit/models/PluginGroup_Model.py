from django.db import models
from .Plugin_Model import Plugin
from .PluginGroupTree_Model import PluginGroupTree
from .PluginSequence_Model import PluginSequence
import logging

logger = logging.getLogger(__name__)


class PluginGroup(models.Model):
    name = models.CharField(max_length=255)
    description = models.CharField(max_length=512, blank=True)
    enabled = models.BooleanField(default=True)

    # ── relations with order / failure‑handling support ───────
    plugin_groups = models.ManyToManyField(
        "self",
        through=PluginGroupTree,
        symmetrical=False,
    )
    plugins = models.ManyToManyField(
        Plugin,
        through=PluginSequence,
        through_fields=("plugingroup", "plugin"),
    )
    # ──────────────────────────────────────────────────────────

    # ---------- helpers ----------
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

    # ---------- diagnostics ----------
    def detail(self):
        logger.info(f"-- PluginGroup '{self}' Detail Info --")
        logger.info(f"ID:\t{self.pk}")
        logger.info(f"NAME:\t{self.name}")
        logger.info(f"DESC:\t{self.description}")
        logger.info(f"Enabled:\t{self.enabled}")
        logger.info(f"PluginGroups List: Count:{self.plugin_groups_count()}")
        for tree in self.child_plugin_groups():
            logger.info(
                f"PluginGroup:{tree.child} Seq:{tree.sequence} "
                f"IgnoreFail:{tree.ignore_fail} ForceExec:{tree.force_exec}"
            )
        logger.info(f"Plugins List: Count:{self.plugins_count()}")
        for seq in self.plugin_sequences():
            logger.info(
                f"Plugin:{seq.plugin} Seq:{seq.sequence} IgnoreFail:{seq.ignore_fail}"
            )
        logger.info(f"++ PluginGroup '{self}' Detail Info Finish ++")

    # ---------- execution ----------
    def execute(self, target=None, parameters=None, force_exec=True):
        """
        Execute this PluginGroup.

        Returns True when all mandatory steps succeed, False otherwise.
        """
        if not self.enabled and not force_exec:
            logger.info(f"PluginGroup {self} is disabled.")
            return True  # treat "skipped" as success

        overall_ok = True

        # 1. child groups
        for tree in self.child_plugin_groups():
            logger.info(f"Executing child PluginGroup: {tree.child}")
            ok = tree.child.execute(target, parameters, tree.force_exec)
            if not ok:
                logger.info(
                    f"Child PluginGroup {tree.child} failed "
                    f"(ignore_fail={tree.ignore_fail})"
                )
                if not tree.ignore_fail:
                    return False
                overall_ok = False

        # 2. plugins
        for seq in self.plugin_sequences():
            logger.info(f"Executing Plugin: {seq.plugin}")
            
            # Use ExploitPluginManager to execute the plugin
            from sat_toolkit.core.exploit_manager import ExploitPluginManager
            plugin_manager = ExploitPluginManager()
            
            try:
                # The execute_plugin method handles both sync and async plugins
                result = plugin_manager.execute_plugin(seq.plugin.name, target, parameters)
                
                # Handle different return types
                if isinstance(result, dict):
                    # For async plugins or structured returns
                    if result.get('execution_type') == 'async':
                        # This is an async task - you might want to wait for it or handle differently
                        logger.warning(f"Plugin {seq.plugin.name} started asynchronously. Group execution may not wait for completion.")
                        ok = True  # Assume success for now since we can't wait
                    else:
                        # Normal structured result
                        ok = result.get('success', True)
                else:
                    # For simple boolean returns
                    ok = bool(result)
                    
            except Exception as e:
                logger.error(f"Error executing plugin {seq.plugin.name}: {str(e)}")
                ok = False
            
            if not ok:
                logger.info(
                    f"Plugin {seq.plugin} failed (ignore_fail={seq.ignore_fail})"
                )
                if not seq.ignore_fail:
                    return False
                overall_ok = False

        return overall_ok