from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/system_usage/$', consumers.SystemUsageConsumer.as_asgi()),
    re_path(r'ws/exploit/(?P<task_id>[^/]+)/$', consumers.ExploitWebsocketConsumer.as_asgi()),
    re_path(r'ws/device/stream/(?P<device_id>[^/]+)/$', consumers.DeviceStreamConsumer.as_asgi()),
]
