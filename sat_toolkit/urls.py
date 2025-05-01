from django.urls import path, re_path, get_resolver
from . import views
from .view_handlers.device_views import (
    device_info,
    get_all_devices,
    scan_all_devices,
    scan_specific_device,
    list_devices,
    initialize_devices,
    cleanup_devices
)
from .view_handlers.vehicle_views import (
    ota_info,
    vehicle_info,
    select_vehicle_profile
)
from .view_handlers.file_views import (
    upload_file,
    list_files,
    download_file,
    delete_file
)

def get_url_patterns():
    """Helper function to get all URL patterns with their names"""
    patterns = []
    
    for pattern in urlpatterns:
        if hasattr(pattern, 'name') and pattern.name:
            # Include all named URLs from our patterns
            method = 'POST' if hasattr(pattern.callback, 'csrf_exempt') else 'GET'
            
            # Get documentation from the view function's docstring
            doc = pattern.callback.__doc__ or ''
            
            patterns.append({
                'name': pattern.name,
                'pattern': f'/api/{str(pattern.pattern)}',  # Add /api/ prefix
                'method': method,
                'description': doc.strip(),
                'deprecated': 'DEPRECATED' in doc
            })
    return patterns

urlpatterns = [
    # New endpoint to list all URLs
    path('list_urls/', views.list_urls, name='list_urls'),

    # Logging configuration
    path('set_log_level/', views.set_log_level, name='set_log_level'),

    # Device-related endpoints (from device_views.py)
    path('device_info/', device_info, name='device_info'),
    path('get_all_devices/', get_all_devices, name='get_all_devices'),

    # DEPRECATED: Use scan_devices/ endpoint instead
    path('scan_all_devices/', scan_all_devices, name='scan_all_devices'),

    path('scan_device/<str:driver_name>/', scan_specific_device, name='scan_specific_device'),
    path('list_devices/', list_devices, name='list_devices'),

    # OTA and vehicle information (from vehicle_views.py)
    path('ota_info/', ota_info, name='ota_info'),
    path('vehicle_info/', vehicle_info, name='vehicle_info'),
    path('select_vehicle_profile/', select_vehicle_profile, name='select_vehicle_profile'),

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
    path('list_targets/', views.list_targets, name='list_targets'),
    path('select_target/', views.select_target, name='select_target'),

    # Exploit
    # path('exploit/', views.exploit, name='exploit'),
    path('execute_plugin/', views.execute_plugin, name='execute_plugin'),

    # Plugin info and groups
    path('list_plugin_info/', views.list_plugin_info, name='list_plugin_info'),
    path('list_groups/', views.list_groups, name='list_groups'),
    path('execute_group/', views.execute_group, name='execute_group'),
    path('stop_plugin_async/', views.stop_plugin_async, name='stop_plugin_async'),

    # Add new endpoints for driver management
    path('get_driver_states/', views.get_driver_states, name='get_driver_states'),
    path('enable_driver/', views.enable_driver, name='enable_driver'),
    path('disable_driver/', views.disable_driver, name='disable_driver'),
    
    # Additional endpoints
    path('active_channels/', views.active_channels, name='active_channels'),
    path('list_device_commands/<str:device_name>/', views.list_device_commands, name='list_device_commands'),
    path('execute_device_command/<str:driver_name>/', views.execute_device_command, name='execute_device_command'),
    path('create_group/', views.create_group, name='create_group'),
    path('delete_group/', views.delete_group, name='delete_group'),

    # Add these new endpoints
    path('initialize_devices/', initialize_devices, name='initialize_devices'),
    path('cleanup_devices/', cleanup_devices, name='cleanup_devices'),
    path('cleanup_plugins/', views.cleanup_plugins, name='cleanup_plugins'),
    
    # Plugin code editor endpoints
    path('get_plugin_code/', views.get_plugin_code, name='get_plugin_code'),
    path('save_plugin_code/', views.save_plugin_code, name='save_plugin_code'),
    
    # Firmware download endpoints
    path('download_firmware/', views.file_download, name='list_firmware_files'),
    path('download_firmware/<path:file_path>', views.file_download, name='download_firmware'),
    
    # New file upload/management endpoints
    path('upload_file/', upload_file, name='upload_file'),
    path('list_files/', list_files, name='list_files'),
    path('download_file/<path:file_path>', download_file, name='download_file'),
    path('download_file/', download_file, name='download_file'),
    path('delete_file/<path:file_path>', delete_file, name='delete_file'),
]
