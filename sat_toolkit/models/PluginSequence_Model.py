from django.db import models
# Remove direct imports of models to prevent circular dependencies


class PluginSequence(models.Model):
    # Use string references to models instead of direct model references
    plugingroup = models.ForeignKey("PluginGroup", on_delete=models.CASCADE)
    plugin = models.ForeignKey("Plugin", on_delete=models.CASCADE)
    sequence = models.SmallIntegerField(default=100)
    ignore_fail = models.BooleanField(
        default=False,
        help_text="Continue execution even if the plugin fails",
    )

    class Meta:
        ordering = ["sequence"]

    def __str__(self):
        return (
            f"[PluginSequence:{self.plugingroup} → {self.plugin} "
            f"Seq:{self.sequence} IgnoreFail:{self.ignore_fail}]"
        )