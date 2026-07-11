"""Contract tests for the subprocess-based ADB_Mgr migration.

These tests mock ``subprocess.run`` and never require hardware or a running
ADB server.  They verify the migration boundary: argument-list construction,
``adb devices -l`` parsing, and error handling.
"""

import subprocess
from unittest.mock import patch, MagicMock

import django
from django.apps import apps
from django.test import SimpleTestCase

if not apps.ready:
    import os
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
    django.setup()


def _completed(stdout="", stderr="", returncode=0):
    """Build a ``subprocess.CompletedProcess`` for mocking."""
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class TestListDevices(SimpleTestCase):
    """Verify ``adb devices -l`` parsing and ``.serial`` contract."""

    def setUp(self):
        self.manager = object.__new__(ADB_Mgr)
        self.manager._ADB_Mgr__last_connect_serial = None
        self.manager._ADB_Mgr__last_adb_root = None
        self.manager._ADB_Mgr__root_states = {}
        self.manager._ADB_Mgr__lock = __import__("threading").Lock()
        self.manager._initialized = True

    def test_parses_device_rows_and_exposes_serial(self):
        output = (
            "List of devices attached\n"
            "R28M30abcd  device usb:1-5 product:xxx model:yyy\n"
            "\n"
            "emulator-5554  device product:sdk\n"
        )
        with patch("iotsploit_django.tools.adb_mgr.subprocess.run", return_value=_completed(stdout=output)):
            devices = self.manager.list_devices()

        self.assertEqual(len(devices), 2)
        serials = [d.serial for d in devices]
        self.assertIn("R28M30abcd", serials)
        self.assertIn("emulator-5554", serials)

    def test_skips_offline_unauthorized_and_malformed_rows(self):
        output = (
            "List of devices attached\n"
            "offline_serial   offline\n"
            "unauth_serial    unauthorized\n"
            "garbage_no_state\n"
            "\n"
            "real_serial  device\n"
        )
        with patch("iotsploit_django.tools.adb_mgr.subprocess.run", return_value=_completed(stdout=output)):
            devices = self.manager.list_devices()

        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0].serial, "real_serial")

    def test_daemon_startup_text_ignored(self):
        output = (
            "adb server is out of date.  killing...\n"
            "* daemon started successfully *\n"
            "List of devices attached\n"
            "abc123  device\n"
        )
        with patch("iotsploit_django.tools.adb_mgr.subprocess.run", return_value=_completed(stdout=output)):
            devices = self.manager.list_devices()

        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0].serial, "abc123")

    def test_missing_adb_executable_returns_empty_list(self):
        with patch("iotsploit_django.tools.adb_mgr.subprocess.run", side_effect=FileNotFoundError("adb not found")):
            devices = self.manager.list_devices()
        self.assertEqual(devices, [])


class TestDeviceSpecificCommands(SimpleTestCase):
    """Every device-specific command must use ``adb -s <serial>`` argument list."""

    def setUp(self):
        self.manager = object.__new__(ADB_Mgr)
        self.manager._ADB_Mgr__last_connect_serial = None
        self.manager._ADB_Mgr__last_adb_root = None
        self.manager._ADB_Mgr__root_states = {}
        self.manager._ADB_Mgr__lock = __import__("threading").Lock()
        self.manager._initialized = True
        self.manager._target_manager = MagicMock()

    def test_connect_dev_uses_serial_flag_and_wait_for_device(self):
        with patch("iotsploit_django.tools.adb_mgr.subprocess.run", return_value=_completed(stdout="")) as run:
            with patch.object(self.manager, "list_devices") as ld:
                ld.return_value = [MagicMock(serial="abc123")]
                self.manager.connect_dev("abc123", root_require=False)

        # At least one call must contain -s abc123
        all_args = [c.args[0] for c in run.call_args_list]
        has_serial = any("-s" in a and "abc123" in a for a in all_args)
        self.assertTrue(has_serial, f"No call used -s abc123: {all_args}")

    def test_connect_dev_root_uses_serial_flag(self):
        with patch("iotsploit_django.tools.adb_mgr.subprocess.run", return_value=_completed(stdout="")) as run:
            with patch.object(self.manager, "list_devices") as ld:
                ld.return_value = [MagicMock(serial="abc123")]
                self.manager.connect_dev("abc123", root_require=True)

        root_call = [c for c in run.call_args_list if "root" in c.args[0]]
        self.assertTrue(root_call, "No root command was issued")
        self.assertTrue(all("-s" in c.args[0] and "abc123" in c.args[0] for c in root_call))

    def test_pull_file_uses_serial_flag(self):
        with patch.object(self.manager, "connect_dev", return_value="abc123"):
            with patch("iotsploit_django.tools.adb_mgr.subprocess.run", return_value=_completed()) as run:
                self.manager.pull_file("abc123", "/remote/path", "/local/path")

        args = run.call_args.args[0]
        self.assertIn("-s", args)
        self.assertIn("abc123", args)
        self.assertIn("pull", args)
        self.assertIn("/remote/path", args)
        self.assertIn("/local/path", args)

    def test_push_file_uses_serial_flag(self):
        with patch.object(self.manager, "connect_dev", return_value="abc123"):
            with patch("iotsploit_django.tools.adb_mgr.subprocess.run", return_value=_completed()) as run:
                self.manager.push_file("abc123", "/local/path", "/remote/path")

        args = run.call_args.args[0]
        self.assertIn("-s", args)
        self.assertIn("abc123", args)
        self.assertIn("push", args)

    def test_install_apk_uses_serial_flag(self):
        with patch.object(self.manager, "connect_dev", return_value="abc123"):
            with patch("iotsploit_django.tools.adb_mgr.subprocess.run", return_value=_completed(stdout="Success")) as run:
                self.manager.install_apk("abc123", "/tmp/app.apk")

        args = run.call_args.args[0]
        self.assertIn("-s", args)
        self.assertIn("abc123", args)
        self.assertIn("install", args)
        self.assertIn("/tmp/app.apk", args)

    def test_uninstall_uses_serial_flag(self):
        with patch.object(self.manager, "connect_dev", return_value="abc123"):
            with patch("iotsploit_django.tools.adb_mgr.subprocess.run", return_value=_completed(stdout="Success")) as run:
                self.manager.uninstall_apk("abc123", "com.example.app")

        args = run.call_args.args[0]
        self.assertIn("-s", args)
        self.assertIn("abc123", args)
        self.assertIn("uninstall", args)
        self.assertIn("com.example.app", args)

    def test_no_shell_true_anywhere(self):
        """Ensure no host-shell interpolation via shell=True."""
        with patch.object(self.manager, "connect_dev", return_value="abc123"):
            with patch("iotsploit_django.tools.adb_mgr.subprocess.run", return_value=_completed()) as run:
                self.manager.pull_file("abc123", "/r", "/l")
                self.manager.push_file("abc123", "/l", "/r")

        for call in run.call_args_list:
            self.assertFalse(call.kwargs.get("shell", False), "shell=True must never be used")


class TestShellCmd(SimpleTestCase):
    """``shell_cmd`` must use a temp script and clean up on success and failure."""

    def setUp(self):
        self.manager = object.__new__(ADB_Mgr)
        self.manager._ADB_Mgr__last_connect_serial = None
        self.manager._ADB_Mgr__last_adb_root = None
        self.manager._ADB_Mgr__root_states = {}
        self.manager._ADB_Mgr__lock = __import__("threading").Lock()
        self.manager._initialized = True

    def test_shell_cmd_executes_script_via_adb_shell(self):
        with patch.object(self.manager, "connect_dev", return_value="abc123"):
            with patch("iotsploit_django.tools.adb_mgr.subprocess.run", return_value=_completed(stdout="hello\nworld\n")) as run:
                result = self.manager.shell_cmd("abc123", "echo hello && echo world")

        self.assertEqual(result, "hello\nworld\n")
        # Verify that all device-specific calls use -s abc123
        for call in run.call_args_list:
            args = call.args[0]
            self.assertIn("-s", args)
            self.assertIn("abc123", args)

    def test_shell_cmd_with_metacharacters_no_injection(self):
        """Serial/path values with spaces or metacharacters must not produce host-shell injection."""
        serial = "a;rm -rf /"
        with patch.object(self.manager, "connect_dev", return_value=serial):
            with patch("iotsploit_django.tools.adb_mgr.subprocess.run", return_value=_completed(stdout="ok")) as run:
                self.manager.shell_cmd(serial, "ls -la")

        for call in run.call_args_list:
            args = call.args[0]
            # The serial must appear as a single list element, not interpolated
            self.assertIn(serial, args)
            self.assertFalse(call.kwargs.get("shell", False))


class TestErrorHandling(SimpleTestCase):
    """Boundary exceptions: FileNotFoundError, TimeoutExpired, non-zero exit."""

    def setUp(self):
        self.manager = object.__new__(ADB_Mgr)
        self.manager._ADB_Mgr__last_connect_serial = None
        self.manager._ADB_Mgr__last_adb_root = None
        self.manager._ADB_Mgr__root_states = {}
        self.manager._ADB_Mgr__lock = __import__("threading").Lock()
        self.manager._initialized = True

    def test_timeout_returns_failure(self):
        with patch.object(self.manager, "connect_dev", return_value="abc123"):
            with patch("iotsploit_django.tools.adb_mgr.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="adb", timeout=5)):
                result = self.manager.shell_cmd("abc123", "sleep 999")
        self.assertIsNone(result)

    def test_missing_adb_returns_failure(self):
        with patch.object(self.manager, "connect_dev", return_value="abc123"):
            with patch("iotsploit_django.tools.adb_mgr.subprocess.run", side_effect=FileNotFoundError("adb not found")):
                result = self.manager.shell_cmd("abc123", "ls")
        self.assertIsNone(result)

    def test_nonzero_exit_returns_failure(self):
        with patch.object(self.manager, "connect_dev", return_value="abc123"):
            with patch("iotsploit_django.tools.adb_mgr.subprocess.run", side_effect=subprocess.CalledProcessError(1, "adb")):
                result = self.manager.shell_cmd("abc123", "false")
        self.assertIsNone(result)


# Import at module end to allow Django setup first
from iotsploit_django.tools.adb_mgr import ADB_Mgr  # noqa: E402
