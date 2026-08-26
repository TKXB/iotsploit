from django.urls import path

from iotsploit_django.web import views


urlpatterns = [
    # Plugin and device management
    path("list_plugins/", views.list_plugins, name="list_plugins"),
    path("list_device_drivers/", views.list_device_drivers, name="list_device_drivers"),
    # Exploit
    path("execute_plugin/", views.execute_plugin, name="execute_plugin"),
    path("identify_can_bus/", views.identify_can_bus, name="identify_can_bus"),
    # Plugin info and groups
    path("list_plugin_info/", views.list_plugin_info, name="list_plugin_info"),
    path("list_groups/", views.list_groups, name="list_groups"),
    path("execute_group/", views.execute_group, name="execute_group"),
    path("stop_plugin_async/", views.stop_plugin_async, name="stop_plugin_async"),
    # Driver management
    path("get_driver_states/", views.get_driver_states, name="get_driver_states"),
    path("enable_driver/", views.enable_driver, name="enable_driver"),
    path("disable_driver/", views.disable_driver, name="disable_driver"),
    # SSOT: exploit plugin enable/disable + groups (for MCP runtime)
    path("plugins/exploits/enabled/", views.list_enabled_exploit_plugins, name="list_enabled_exploit_plugins"),
    path("plugins/exploits/discovered/", views.discovered_exploit_plugins, name="discovered_exploit_plugins"),
    path(
        "plugins/exploits/<str:name>/enable/",
        views.enable_exploit_plugin,
        name="enable_exploit_plugin",
    ),
    path(
        "plugins/exploits/<str:name>/disable/",
        views.disable_exploit_plugin,
        name="disable_exploit_plugin",
    ),
    path("plugin_groups/enabled/", views.list_enabled_plugin_groups, name="list_enabled_plugin_groups"),
    path("plugin_groups/<str:name>/", views.get_plugin_group, name="get_plugin_group"),
    # Device command endpoints
    path("list_device_commands/<str:device_name>/", views.list_device_commands, name="list_device_commands"),
    path(
        "execute_device_command/<str:driver_name>/",
        views.execute_device_command,
        name="execute_device_command",
    ),
    # Plugin group CRUD
    path("create_group/", views.create_group, name="create_group"),
    path("delete_group/", views.delete_group, name="delete_group"),
    # Plugin cleanup
    path("cleanup_plugins/", views.cleanup_plugins, name="cleanup_plugins"),
    # Plugin code editor endpoints
    path("get_plugin_code/", views.get_plugin_code, name="get_plugin_code"),
    path("save_plugin_code/", views.save_plugin_code, name="save_plugin_code"),
]

