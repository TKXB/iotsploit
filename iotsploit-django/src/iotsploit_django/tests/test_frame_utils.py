from unittest import TestCase

from iotsploit_django.tools.frame_utils import frame_data_from_fields


class TestFrameDataFromFields(TestCase):
    def test_serializes_hex_text_and_empty_fields(self):
        fields = [
            {"value": "0x0102"},
            {"value": "ff"},
            {"value": "plain text"},
            {"value": ""},
            {},
        ]

        self.assertEqual(frame_data_from_fields(fields), b"\x01\x02\xffplain text")

    def test_returns_empty_bytes_for_invalid_field_shape(self):
        self.assertEqual(frame_data_from_fields([None]), b"")
