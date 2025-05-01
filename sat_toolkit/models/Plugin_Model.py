from django.db import models
import importlib


class Plugin(models.Model):
    name = models.CharField(max_length=255)
    description = models.CharField(max_length=512, blank=True)
    enabled = models.BooleanField(default=True)
    module_path = models.CharField(
        max_length=255, help_text="Python module path to the plugin class"
    )
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

    # ---------- execution ----------
    def execute(self, target=None, parameters=None):
        """
        Run the concrete plugin implementation.

        Returns:
            bool – success flag (None is treated as success).
        """
        if not self.enabled:
            # disabled is considered “success” so parent can continue if desired
            return True

        plugin_instance = self.get_plugin_instance()
        result = plugin_instance.execute(target, parameters)
        return True if result is None else bool(result)

    # ---------- utilities ----------
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