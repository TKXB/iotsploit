from django.db import models


class PluginGroupTree(models.Model):
    parent = models.ForeignKey(
        "PluginGroup", on_delete=models.CASCADE, related_name="parent"
    )
    child = models.ForeignKey(
        "PluginGroup", on_delete=models.CASCADE, related_name="child"
    )

    # ── order / failure‑handling ──────────────────────────────
    sequence = models.SmallIntegerField(default=100)
    ignore_fail = models.BooleanField(
        default=False,
        help_text="Continue execution even if the child group fails",
    )
    # ──────────────────────────────────────────────────────────
    force_exec = models.BooleanField(default=False)

    class Meta:
        ordering = ["sequence"]

    def __str__(self):
        return (
            f"[Parent:{self.parent} Child:{self.child} "
            f"Seq:{self.sequence} IgnoreFail:{self.ignore_fail} "
            f"ForceExec:{self.force_exec}]"
        )