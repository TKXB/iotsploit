from django.urls import path

from . import views

urlpatterns = [
    path("device_info", views.device_info),
    path("ota_info", views.ota_info),
    path("vehicle_info", views.vehicle_info),
    path("select_vehicle_profile", views.select_vehicle_profile),
    path("request_enter_test_page", views.request_enter_test_page),
    path("request_exit_test_page", views.request_exit_test_page),

    path("request_test_status", views.request_test_status),

    path("select_test_level", views.select_test_level),
    path("select_test_project", views.select_test_project),

    path("user_input", views.user_input),

    path("start_test", views.start_test),
    path("stop_test", views.stop_test),

    path("record_user_input", views.record_user_input),
    

]
