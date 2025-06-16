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
from .view_handlers.vehicle_views import ota_info
from .view_handlers.file_views import (
    upload_file,
    list_files,
    download_file,
    delete_file
)
from .view_handlers.console_logs_views import (
    get_console_logs,
    clear_console_logs,
    control_console_reader
)
from .view_handlers.ai_model_views import (
    ai_model_list,
    ai_model_create,
    ai_model_detail,
    ai_model_update,
    ai_model_delete,
    ai_model_test_connection,
    ai_model_set_default,
    ai_template_list,
    ai_provider_list
)
from .view_handlers.target_views import (
    list_targets,
    select_target,
    edit_target,
    create_target,
    delete_target,
    get_current_target
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
    # AI Model Configuration endpoints
    path('ai-models/', ai_model_list, name='ai_model_list'),
    path('ai-models/create/', ai_model_create, name='ai_model_create'),
    path('ai-models/<int:pk>/', ai_model_detail, name='ai_model_detail'),
    path('ai-models/<int:pk>/update/', ai_model_update, name='ai_model_update'),
    path('ai-models/<int:pk>/delete/', ai_model_delete, name='ai_model_delete'),
    path('ai-models/<int:pk>/test/', ai_model_test_connection, name='ai_model_test_connection'),
    path('ai-models/<int:pk>/set-default/', ai_model_set_default, name='ai_model_set_default'),
    path('ai-models/providers/', ai_provider_list, name='ai_provider_list'),
    path('ai-templates/', ai_template_list, name='ai_template_list'),
    
    # New endpoint to list all URLs
    path('list_urls/', views.list_urls, name='list_urls'),

    # Logging configuration
    path('set_log_level/', views.set_log_level, name='set_log_level'),
    
    # Console logs endpoints
    path('console_logs/', get_console_logs, name='get_console_logs'),
    path('console_logs/clear/', clear_console_logs, name='clear_console_logs'),
    path('console_logs/control/', control_console_reader, name='control_console_reader'),

    # Device-related endpoints (from device_views.py)
    path('device_info/', device_info, name='device_info'),
    path('get_all_devices/', get_all_devices, name='get_all_devices'),

    # DEPRECATED: Use scan_devices/ endpoint instead
    path('scan_all_devices/', scan_all_devices, name='scan_all_devices'),

    path('scan_device/<str:driver_name>/', scan_specific_device, name='scan_specific_device'),
    path('list_devices/', list_devices, name='list_devices'),

    # OTA and vehicle information (from vehicle_views.py)
    path('ota_info/', ota_info, name='ota_info'),

    # Plugin and device management
    path('list_plugins/', views.list_plugins, name='list_plugins'),
    path('list_device_drivers/', views.list_device_drivers, name='list_device_drivers'),
    
    # Target management
    path('list_targets/', list_targets, name='list_targets'),
    path('select_target/', select_target, name='select_target'),
    path('edit_target/', edit_target, name='edit_target'),
    path('create_target/', create_target, name='create_target'),
    path('delete_target/', delete_target, name='delete_target'),
    path('get_current_target/', get_current_target, name='get_current_target'),

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
    
    # Tool status and management endpoints
    path('tools_status/', views.get_tools_status, name='get_tools_status'),
    path('tools/refresh/', views.refresh_tools, name='refresh_tools'),
    path('tools/<str:tool_name>/', views.get_tool_details, name='get_tool_details'),
    path('system_health/', views.get_system_health, name='get_system_health'),
    
    # Recovery operation endpoints
    path('recovery/drivers/', views.list_recovery_drivers, name='list_recovery_drivers'),
    path('recovery/<str:driver_name>/', views.execute_recovery, name='execute_recovery'),
]
