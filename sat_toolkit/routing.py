from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/system_usage/$', consumers.SystemUsageConsumer.as_asgi()),
    re_path(r'ws/exploit/(?P<task_id>[^/]+)/$', consumers.ExploitWebsocketConsumer.as_asgi()),
    re_path(r'ws/device/stream/(?P<channel>[^/]+)/$', consumers.DeviceStreamConsumer.as_asgi()),
    re_path(r'ws/console_logs/$', consumers.ConsoleLogsConsumer.as_asgi()),
]
