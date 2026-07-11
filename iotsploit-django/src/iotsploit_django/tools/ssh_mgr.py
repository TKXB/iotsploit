"""SSH manager using Paramiko.

Replaces the former pwntools-based SSH manager.  The old code was internally
inconsistent — ``open_ssh()`` returned a pwntools ``process`` tube while
``close_ssh()`` and ``ssh_cmd()`` expected a pwntools ``ssh`` tube object.
This rewrite uses a proper ``paramiko.SSHClient`` throughout.

Security note: ``AutoAddPolicy`` matches the old ``StrictHostKeyChecking=no``
behaviour.  It does **not** authenticate the server.  A known-hosts policy
should be configured separately when a credential design is available.
"""

import logging
from typing import Any

import paramiko

from iotsploit_django.tools.sat_utils import *

logger = logging.getLogger(__name__)


class SSH_Mgr:
    """SSH connection manager backed by Paramiko."""

    __ssh_connect_timeout_S = 10
    __ssh_cmd_timeout_S = 30

    @staticmethod
    def Instance():
        return _instance

    def __init__(self):
        self.__ssh_dict = {}

    def open_ssh(self, ip: str, user: str, passwd: str):
        """Open an SSH connection.

        Args:
            ip: Target host IP address.
            user: SSH username.
            passwd: SSH password.

        Returns:
            ``paramiko.SSHClient`` on success, ``None`` on failure.
        """
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=ip,
                username=user,
                password=passwd,
                timeout=self.__ssh_connect_timeout_S,
                banner_timeout=self.__ssh_connect_timeout_S,
                auth_timeout=self.__ssh_connect_timeout_S,
            )
            logger.info(f"SSH Connect {ip} Success.")
            return client
        except Exception:
            logger.exception(f"SSH Connect {ip} Fail!")
            try:
                client.close()
            except Exception:
                pass
            return None

    def close_ssh(self, ssh_context: Any):
        """Close an SSH connection.

        Safe for ``None`` and idempotent on repeated calls.
        """
        if ssh_context is None:
            return
        try:
            ssh_context.close()
        except Exception:
            pass
        return

    def ssh_cmd(self, ssh_context: Any, ssh_cmd: str):
        """Execute a command over SSH.

        Args:
            ssh_context: ``paramiko.SSHClient`` from ``open_ssh()``.
            ssh_cmd: Command string to execute remotely.

        Returns:
            Decoded stdout on success (exit status 0), ``None`` on failure.
        """
        if ssh_context is None:
            logger.error("SSH Context Invalid!")
            return None

        try:
            stdin, stdout, stderr = ssh_context.exec_command(ssh_cmd, timeout=self.__ssh_cmd_timeout_S)
            exit_status = stdout.channel.recv_exit_status()
            out = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace")

            if exit_status != 0:
                logger.error(f"SSH Command failed (exit={exit_status}). CMD: {ssh_cmd}\nstderr: {err}")
                return None

            logger.info(f"SSH Run CMD Success. CMD: {ssh_cmd}\nResult:\n{out}")
            return out
        except Exception:
            logger.exception(f"SSH Run CMD Fail! CMD: {ssh_cmd}")
            return None


_instance = SSH_Mgr()
