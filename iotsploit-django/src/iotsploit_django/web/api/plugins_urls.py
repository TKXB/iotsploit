from django.urls import path

from iotsploit_django.web import views


urlpatterns = [
    # Plugin and device management
    path("list_plugins/", views.list_plugins, name="list_plugins"),
    path("list_device_drivers/", views.list_device_drivers, name="list_device_drivers"),
    # Exploit
    path("execute_plugin/", views.execute_plugin, name="execute_plugin"),
    # Plugin info and groups
    path("list_plugin_info/", views.list_plugin_info, name="list_plugin_info"),
    path("list_groups/", views.list_groups, name="list_groups"),
    path("execute_group/", views.execute_group, name="execute_group"),
    path("stop_plugin_async/", views.stop_plugin_async, name="stop_plugin_async"),
    # Driver management
    path("get_driver_states/", views.get_driver_states, name="get_driver_states"),
    path("enable_driver/", views.enable_driver, name="enable_driver"),
    path("disable_driver/", views.disable_driver, name="disable_driver"),
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


