import os
import sys
import django

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sat_django_entry.settings')
django.setup()

import logging
from sat_toolkit.models.Plugin_Model import Plugin
from sat_toolkit.models.PluginGroup_Model import PluginGroup
from sat_toolkit.models.PluginGroupTree_Model import PluginGroupTree
from sat_toolkit.core.exploit_manager import ExploitPluginManager

logger = logging.getLogger(__name__)

if __name__ == '__main__':

    # Create plugins
    plugin1, created = Plugin.objects.get_or_create(
        name='Plugin 1',
        defaults={
            'description': 'First plugin',
            'enabled': True,
            'module_path': 'plugins.exploits.plugin_adb.TCAMCheckPlugin'  # Adjust the module path accordingly
        }
    )
    plugin2, created = Plugin.objects.get_or_create(
        name='Plugin 2',
        defaults={
            'description': 'Second plugin',
            'enabled': True,
            'module_path': 'plugins.exploits.plugin_ssh.SSHPlugin'  # Adjust the module path accordingly
        }
    )

    # Create plugin groups
    group1, created = PluginGroup.objects.get_or_create(
        name='Group 1',
        defaults={'description': 'First group', 'enabled': True}
    )
    group2, created = PluginGroup.objects.get_or_create(
        name='Group 2',
        defaults={'description': 'Second group', 'enabled': True}
    )

    # Add plugins to groups
    group1.plugins.add(plugin1)
    group2.plugins.add(plugin2)

    # Nest groups
    PluginGroupTree.objects.get_or_create(
        parent=group1,
        child=group2,
        defaults={'force_exec': True}
    )

    # Execute a group
    exploit_manager = ExploitPluginManager()
    exploit_manager.execute_plugin_group('Group 1')