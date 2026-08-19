from django.urls import re_path

from iotsploit_django.websocket import consumers
from iotsploit_django.websocket.ai_assistant_consumer import AIAssistantConsumer


# Keep WS contract stable (see docs/contracts/ws_routes.json).
websocket_urlpatterns = [
    re_path(r"ws/system_usage/$", consumers.SystemUsageConsumer.as_asgi()),
    re_path(r"ws/exploit/(?P<task_id>[^/]+)/$", consumers.ExploitWebsocketConsumer.as_asgi()),
    # Interactive-capable executions, addressed by their own id rather than
    # a Celery task id. Carries prompts as well as status.
    re_path(r"ws/execution/(?P<execution_id>[^/]+)/$", consumers.PluginExecutionConsumer.as_asgi()),
    re_path(r"ws/device/stream/(?P<channel>[^/]+)/$", consumers.DeviceStreamConsumer.as_asgi()),
    re_path(r"ws/console_logs/$", consumers.ConsoleLogsConsumer.as_asgi()),
    re_path(r"ws/ai-assistant/(?P<session_id>\w+)/$", AIAssistantConsumer.as_asgi()),
    # IoT Fuzzer WebSocket endpoints
    re_path(r"ws/iot-fuzzer/testing/$", consumers.IoTFuzzerTestingConsumer.as_asgi()),
    re_path(r"ws/iot-fuzzer/testing/(?P<campaign_id>[^/]+)/$", consumers.IoTFuzzerTestingConsumer.as_asgi()),
    re_path(r"ws/iot-fuzzer/results/$", consumers.IoTFuzzerResultsConsumer.as_asgi()),
    re_path(r"ws/iot-fuzzer/results/(?P<campaign_id>[^/]+)/$", consumers.IoTFuzzerResultsConsumer.as_asgi()),
]


