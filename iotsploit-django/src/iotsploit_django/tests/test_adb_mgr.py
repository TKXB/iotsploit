import os
from unittest.mock import patch

import django
from django.apps import apps
from django.test import SimpleTestCase


if not apps.ready:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
    django.setup()

from iotsploit_django.tools.adb_mgr import ADB_Mgr


class TestADBPermissionQueries(SimpleTestCase):
    def setUp(self):
        self.manager = object.__new__(ADB_Mgr)

    def test_public_queries_delegate_with_existing_modes(self):
        with patch.object(self.manager, "_query_permissions", return_value=[]) as query:
            self.manager.query_dirs_permission_writable_by_any_user("serial", "/", "cache*", ["/proc"], ["sid"])
            query.assert_called_once_with("serial", "/", 2, "d", "cache*", ["/proc"], ["sid"])

        with patch.object(self.manager, "_query_permissions", return_value=[]) as query:
            self.manager.query_files_permission_readable_by_any_user("serial", "/data")
            query.assert_called_once_with("serial", "/data", 4, "f", "", [], [])

        with patch.object(self.manager, "_query_permissions", return_value=[]) as query:
            self.manager.query_files_permission_writable_by_any_user("serial", "/data")
            query.assert_called_once_with("serial", "/data", 2, "f", "", [], [])

    def test_permission_query_preserves_command_and_filter_inputs(self):
        items = [{"filepath": "/data/file", "sid": "allowed"}]
        with (
            patch.object(self.manager, "connect_dev", return_value=object()),
            patch.object(self.manager, "shell_cmd", return_value="listing") as shell,
            patch.object(self.manager, "query_android_selinux_status", return_value=True),
            patch.object(self.manager, "query_writable_mount_dirs", return_value=["/data/"]) as mounts,
            patch.object(self.manager, "_parse_permission_listings", return_value=items),
            patch.object(self.manager, "_filter_file_items", return_value=items) as filter_items,
        ):
            result = self.manager._query_permissions("serial", "/data", 2, "d", "cache*", ["/proc"], ["sid"])

        shell.assert_called_once_with(
            "serial",
            'find /data -perm -2 -type d -name "cache*" -print0 2>/dev/null | xargs -0 -r ls -d -l -Z 2>/dev/null',
        )
        mounts.assert_called_once_with("serial")
        filter_items.assert_called_once_with(items, ["/proc"], ["sid"], True, ["/data/"], is_dir=True)
        self.assertEqual(result, items)
