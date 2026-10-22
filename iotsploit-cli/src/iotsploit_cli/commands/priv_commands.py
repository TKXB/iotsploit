from __future__ import annotations

import os
import subprocess

import cmd2

from iotsploit_priv.client import VERB_TABLE_HASH
from iotsploit_priv.native import (
    INSTALLER,
    current_user,
    install_manifest,
    native_status,
    sha256_file,
    verb_lines,
)
from iotsploit_core.core.tool_manager import PathResolver

from .base_commands import BaseCommands


priv_parser = cmd2.Cmd2ArgumentParser(description="Manage the bounded privileged helper")
priv_sub = priv_parser.add_subparsers(dest="action", required=True)
priv_status = priv_sub.add_parser("status", help="verify native helper health and integrity")
priv_status.add_argument("--service-user", default=None, help="account to check (default: the invoking user)")
priv_status.set_defaults(handler="status")
priv_install = priv_sub.add_parser("install", help="install the native helper")
priv_install.add_argument("--service-user", default=None, help="account to grant access (default: the invoking user)")
priv_install.add_argument("--worker-unit", action="append", default=[])
priv_install.set_defaults(handler="install")
priv_uninstall = priv_sub.add_parser("uninstall", help="remove the native helper")
priv_uninstall.add_argument("--worker-unit", action="append", default=[])
priv_uninstall.set_defaults(handler="uninstall")
priv_sub.add_parser("verbs", help="show the fixed helper vocabulary").set_defaults(handler="verbs")


class PrivCommands(BaseCommands):
    """Native privileged-helper lifecycle commands."""

    def _confirm(self, action: str) -> bool:
        answer = self.read_input(f"{action} the privileged helper? [y/N] ")
        return answer.strip().lower() in {"y", "yes"}

    def _run_installer(self, action: str, service_user: str | None, worker_units: list[str]) -> int:
        if os.path.exists("/.dockerenv"):
            self.perror("Container helper files are managed by the image; native install commands are disabled.")
            return 2
        if action == "install":
            self.poutput("Native privileged helper installation:")
            for source, destination, mode in install_manifest():
                self.poutput(f"  {source} -> {destination} root:root {mode:04o} sha256={sha256_file(source)}")
            self.poutput(f"  verb table sha256={VERB_TABLE_HASH}")
        else:
            self.poutput("Native privileged helper removal:")
            for _, destination, _ in install_manifest():
                self.poutput(f"  remove {destination}")
            self.poutput("  remove /run/iotsploit if empty; retain the iotsploit group")
        if not self._confirm(action.capitalize()):
            self.poutput("Cancelled.")
            return 1
        sudo = PathResolver().resolve_tool_path("sudo")
        if not sudo:
            self.perror("Required tool is unavailable: sudo")
            return 2
        argv = [sudo, os.fspath(INSTALLER), action]
        if service_user is not None:
            argv.extend(["--service-user", service_user])
        for unit in worker_units:
            argv.extend(["--worker-unit", unit])
        return subprocess.run(argv, check=False).returncode

    @cmd2.with_category("IoTSploit Commands")
    @cmd2.with_argparser(priv_parser)
    def do_priv(self, args):
        """Inspect or manage the bounded privileged helper."""
        if args.handler == "verbs":
            for line in verb_lines():
                self.poutput(line)
            self.poutput(f"sha256: {VERB_TABLE_HASH}")
            self.last_result = 0
        elif args.handler == "status":
            status = native_status(args.service_user)
            for line in status.lines:
                (self.poutput if status.code == 0 else self.perror)(line)
            self.last_result = status.code
        elif args.handler == "install":
            self.last_result = self._run_installer(
                "install", args.service_user or current_user(), args.worker_unit
            )
        else:
            self.last_result = self._run_installer("uninstall", None, args.worker_unit)
