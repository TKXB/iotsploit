"""Contract tests for the Paramiko-based SSH manager migration.

These tests mock ``paramiko.SSHClient`` and its streams/channels; they never
open a network connection.  They cover both the Django ``SSH_Mgr`` and the
exploits plugin ``SSH_Mgr`` / ``SSHPlugin``.
"""

from unittest.mock import patch, MagicMock

import django
from django.apps import apps
from django.test import SimpleTestCase

if not apps.ready:
    import os
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
    django.setup()


def _mock_ssh_client(stdout_bytes=b"ok\n", stderr_bytes=b"", exit_status=0):
    """Build a mock ``paramiko.SSHClient`` whose ``exec_command`` returns
    streams that yield *stdout_bytes*, *stderr_bytes*, and *exit_status*."""
    client = MagicMock()
    stdout = MagicMock()
    stdout.read.return_value = stdout_bytes
    stdout.channel.recv_exit_status.return_value = exit_status
    stderr = MagicMock()
    stderr.read.return_value = stderr_bytes
    client.exec_command.return_value = (MagicMock(), stdout, stderr)
    return client


# ── Django SSH_Mgr tests ─────────────────────────────────────────────────

class TestDjangoSSHMgrConnect(SimpleTestCase):
    """Verify connect arguments, timeout, and cleanup on partial failure."""

    def setUp(self):
        from iotsploit_django.tools.ssh_mgr import SSH_Mgr
        self.mgr = object.__new__(SSH_Mgr)
        self.mgr._initialized = True

    def test_connect_passes_host_user_password_timeout(self):
        with patch("iotsploit_django.tools.ssh_mgr.paramiko.SSHClient") as SSHClient:
            SSHClient.return_value = _mock_ssh_client()
            result = self.mgr.open_ssh("192.168.1.1", "root", "pass123")

        SSHClient.return_value.connect.assert_called_once()
        kw = SSHClient.return_value.connect.call_args.kwargs
        self.assertEqual(kw.get("hostname") or kw.get("ip"), "192.168.1.1")
        self.assertEqual(kw.get("username"), "root")
        self.assertEqual(kw.get("password"), "pass123")
        self.assertIn("timeout", kw)
        self.assertIsNotNone(result)

    def test_auth_failure_returns_none_and_closes_client(self):
        import paramiko
        with patch("iotsploit_django.tools.ssh_mgr.paramiko.SSHClient") as SSHClient:
            client = MagicMock()
            client.connect.side_effect = paramiko.AuthenticationException("bad creds")
            SSHClient.return_value = client
            result = self.mgr.open_ssh("10.0.0.1", "user", "wrong")

        self.assertIsNone(result)
        client.close.assert_called_once()

    def test_connect_exception_returns_none_and_closes_client(self):
        with patch("iotsploit_django.tools.ssh_mgr.paramiko.SSHClient") as SSHClient:
            client = MagicMock()
            client.connect.side_effect = Exception("connection refused")
            SSHClient.return_value = client
            result = self.mgr.open_ssh("10.0.0.2", "user", "pw")

        self.assertIsNone(result)
        client.close.assert_called_once()


class TestDjangoSSHMgrCmd(SimpleTestCase):
    """Verify command execution reads stdout/stderr and waits for exit status."""

    def setUp(self):
        from iotsploit_django.tools.ssh_mgr import SSH_Mgr
        self.mgr = object.__new__(SSH_Mgr)
        self.mgr._initialized = True

    def test_successful_command_returns_decoded_stdout(self):
        client = _mock_ssh_client(stdout_bytes=b"hello\nworld\n")
        result = self.mgr.ssh_cmd(client, "ls -l")

        self.assertEqual(result, "hello\nworld\n")
        client.exec_command.assert_called_once()

    def test_nonzero_exit_returns_none(self):
        client = _mock_ssh_client(stdout_bytes=b"", stderr_bytes=b"command not found", exit_status=127)
        result = self.mgr.ssh_cmd(client, "badcmd")

        self.assertIsNone(result)

    def test_utf8_decode_uses_explicit_error_policy(self):
        """Non-UTF-8 bytes should not crash; errors='replace' or 'ignore' is acceptable."""
        client = _mock_ssh_client(stdout_bytes=b"\xff\xfeok\n", exit_status=0)
        result = self.mgr.ssh_cmd(client, "cat /bin/sh")
        # Should not raise; result is a string
        self.assertIsInstance(result, str)

    def test_exec_command_passes_timeout(self):
        client = _mock_ssh_client()
        self.mgr.ssh_cmd(client, "ls")

        kw = client.exec_command.call_args.kwargs
        self.assertIn("timeout", kw)


class TestDjangoSSHMgrClose(SimpleTestCase):
    """``close_ssh`` must be safe for None and idempotent."""

    def setUp(self):
        from iotsploit_django.tools.ssh_mgr import SSH_Mgr
        self.mgr = object.__new__(SSH_Mgr)
        self.mgr._initialized = True

    def test_close_none_is_harmless(self):
        self.mgr.close_ssh(None)  # must not raise

    def test_repeated_close_is_harmless(self):
        client = MagicMock()
        self.mgr.close_ssh(client)
        self.mgr.close_ssh(client)  # must not raise


# ── Plugin SSH_Mgr / SSHPlugin tests ─────────────────────────────────────

class TestPluginSSHMgrConnect(SimpleTestCase):
    """Verify the exploits-package SSH manager connect contract."""

    def setUp(self):
        from iotsploit_exploits.plugin_ssh import SSH_Mgr as PluginSSH_Mgr
        self.mgr = object.__new__(PluginSSH_Mgr)
        self.mgr._initialized = True

    def test_connect_passes_host_user_password_timeout(self):
        with patch("iotsploit_exploits.plugin_ssh.paramiko.SSHClient") as SSHClient:
            SSHClient.return_value = _mock_ssh_client()
            result = self.mgr.open_ssh("192.168.2.1", "root", "secret")

        SSHClient.return_value.connect.assert_called_once()
        kw = SSHClient.return_value.connect.call_args.kwargs
        self.assertEqual(kw.get("hostname") or kw.get("ip"), "192.168.2.1")
        self.assertEqual(kw.get("username"), "root")
        self.assertEqual(kw.get("password"), "secret")
        self.assertIn("timeout", kw)
        self.assertIsNotNone(result)

    def test_auth_failure_returns_none_and_closes(self):
        import paramiko
        with patch("iotsploit_exploits.plugin_ssh.paramiko.SSHClient") as SSHClient:
            client = MagicMock()
            client.connect.side_effect = paramiko.AuthenticationException("bad")
            SSHClient.return_value = client
            result = self.mgr.open_ssh("10.0.0.3", "user", "bad")

        self.assertIsNone(result)
        client.close.assert_called_once()


class TestPluginSSHMgrCmd(SimpleTestCase):
    """Verify plugin SSH command execution and non-zero exit behaviour."""

    def setUp(self):
        from iotsploit_exploits.plugin_ssh import SSH_Mgr as PluginSSH_Mgr
        self.mgr = object.__new__(PluginSSH_Mgr)
        self.mgr._initialized = True

    def test_successful_command_returns_decoded_stdout(self):
        client = _mock_ssh_client(stdout_bytes=b"result line\n")
        out = self.mgr.ssh_cmd(client, "uname -a")
        self.assertEqual(out, "result line\n")

    def test_nonzero_exit_returns_none(self):
        client = _mock_ssh_client(stdout_bytes=b"", stderr_bytes=b"err", exit_status=1)
        out = self.mgr.ssh_cmd(client, "false")
        self.assertIsNone(out)


class TestPluginSSHMgrClose(SimpleTestCase):
    """Plugin ``close_ssh`` must be safe for None and idempotent."""

    def setUp(self):
        from iotsploit_exploits.plugin_ssh import SSH_Mgr as PluginSSH_Mgr
        self.mgr = object.__new__(PluginSSH_Mgr)
        self.mgr._initialized = True

    def test_close_none_is_harmless(self):
        self.mgr.close_ssh(None)

    def test_repeated_close_is_harmless(self):
        client = MagicMock()
        self.mgr.close_ssh(client)
        self.mgr.close_ssh(client)


class TestSSHPluginNonZeroResult(SimpleTestCase):
    """A non-zero remote command must produce a failed ``ExploitResult``."""

    def test_nonzero_remote_command_produces_failed_result(self):
        from iotsploit_exploits.plugin_ssh import SSHPlugin
        from iotsploit_core.core.exploit_spec import ExploitResult

        plugin = SSHPlugin()
        plugin.ssh_mgr = MagicMock()
        client = _mock_ssh_client(stdout_bytes=b"", stderr_bytes=b"err", exit_status=1)
        plugin.ssh_mgr.open_ssh.return_value = client
        plugin.ssh_mgr.ssh_cmd.return_value = None  # non-zero → None
        plugin.ssh_mgr.close_ssh = MagicMock()

        result = plugin.execute(
            target={"ip_address": "192.168.1.99"},
            parameters={"user": "root", "passwd": "pw", "cmd": "false"},
        )

        self.assertIsInstance(result, ExploitResult)
        self.assertFalse(result.success)

    def test_successful_command_produces_successful_result(self):
        from iotsploit_exploits.plugin_ssh import SSHPlugin
        from iotsploit_core.core.exploit_spec import ExploitResult

        plugin = SSHPlugin()
        plugin.ssh_mgr = MagicMock()
        plugin.ssh_mgr.open_ssh.return_value = _mock_ssh_client(stdout_bytes=b"ok\n")
        plugin.ssh_mgr.ssh_cmd.return_value = "ok\n"
        plugin.ssh_mgr.close_ssh = MagicMock()

        result = plugin.execute(
            target={"ip_address": "192.168.1.99"},
            parameters={"user": "root", "passwd": "pw", "cmd": "echo ok"},
        )

        self.assertIsInstance(result, ExploitResult)
        self.assertTrue(result.success)
