from django.urls import path, re_path
from . import views
from sat_toolkit.consumers import SystemUsageConsumer

urlpatterns = [
    # Device and vehicle information
    path('device_info/', views.device_info, name='device_info'),
    path('ota_info/', views.ota_info, name='ota_info'),
    path('vehicle_info/', views.vehicle_info, name='vehicle_info'),
    path('select_vehicle_profile/', views.select_vehicle_profile, name='select_vehicle_profile'),

    # Test page requests
    path('request_enter_test_page/', views.request_enter_test_page, name='request_enter_test_page'),
    path('request_exit_test_page/', views.request_exit_test_page, name='request_exit_test_page'),
    path('request_test_status/', views.request_test_status, name='request_test_status'),

    # Test selection
    path('select_test_level/', views.select_test_level, name='select_test_level'),
    path('select_test_project/', views.select_test_project, name='select_test_project'),

    # User input
    path('user_input/', views.user_input, name='user_input'),
    path('record_user_input/', views.record_user_input, name='record_user_input'),

    # Test control
    path('start_test/', views.start_test, name='start_test'),
    path('stop_test/', views.stop_test, name='stop_test'),

    # Plugin and device management
    path('list_plugins/', views.list_plugins, name='list_plugins'),
    path('list_device_drivers/', views.list_device_drivers, name='list_device_drivers'),
    path('get_all_devices/', views.get_all_devices, name='get_all_devices'),  # New URL pattern
    path('list_targets/', views.list_targets, name='list_targets'),
    path('select_target', views.select_target, name='select_target'),
    path('scan_all_devices/', views.scan_all_devices, name='scan_all_devices'),

    # Exploit
    path('exploit/', views.exploit, name='exploit'),
    path('execute_plugin/', views.execute_plugin, name='execute_plugin'),  # Added trailing slash

    # Add this to the urlpatterns list
    path('list_plugin_info/', views.list_plugin_info, name='list_plugin_info'),
    path('list_groups/', views.list_groups, name='list_groups'),

    path('execute_plugin_async/', views.execute_plugin_async, name='execute_plugin_async'),
    path('stop_plugin_async/', views.stop_plugin_async, name='stop_plugin_async'),

    # Add this new URL pattern
    path('active_channels/', views.active_channels, name='active_channels'),

    # Add this new URL pattern
    path('list_device_commands/<str:device_name>/', views.list_device_commands, name='list_device_commands'),

    # Add this new URL pattern
    path('execute_device_command/<str:device_name>/', views.execute_device_command, name='execute_device_command'),

    # Add this new URL pattern
    path('create_group/', views.create_group, name='create_group'),
]
