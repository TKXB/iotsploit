from django.urls import path
from . import views

urlpatterns = [
    # 设备和车辆信息
    path("device_info", views.device_info),
    path("ota_info", views.ota_info),
    path("vehicle_info", views.vehicle_info),
    path("select_vehicle_profile", views.select_vehicle_profile),

    # 测试页面请求
    path("request_enter_test_page", views.request_enter_test_page),
    path("request_exit_test_page", views.request_exit_test_page),
    path("request_test_status", views.request_test_status),

    # 测试选择
    path("select_test_level", views.select_test_level),
    path("select_test_project", views.select_test_project),

    # 用户输入
    path("user_input", views.user_input),
    path("record_user_input", views.record_user_input),

    # 测试控制
    path("start_test", views.start_test),
    path("stop_test", views.stop_test),
]
