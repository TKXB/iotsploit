import inspect
from unittest import TestCase

from iotsploit_django.tools.iot_fuzzer_manager import IoTFuzzerManager
from iotsploit_django.tools.iot_fuzzer_service import IoTFuzzerService


class TestFuzzerServiceRuntimeBoundary(TestCase):
    def test_service_and_runtime_manager_have_disjoint_public_operations(self):
        ignored = {"get_instance"}

        def public_operations(cls):
            return {
                name
                for name, member in inspect.getmembers(cls, inspect.isfunction)
                if not name.startswith("_") and name not in ignored
            }

        service_operations = public_operations(IoTFuzzerService)
        manager_operations = public_operations(IoTFuzzerManager)

        self.assertFalse(service_operations & manager_operations)
        self.assertTrue({"create_test_group", "save_protocol_config", "export_test_data"} <= service_operations)
        self.assertTrue({"start_campaign", "pause_campaign", "update_campaign_progress"} <= manager_operations)
