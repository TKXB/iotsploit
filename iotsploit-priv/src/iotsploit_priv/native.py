from __future__ import annotations

import getpass
import grp
import hashlib
import json
import os
import pwd
import socket
import stat
from dataclasses import dataclass
from pathlib import Path

from .client import DEFAULT_SOCKET_PATH, VERB_SCHEMAS, VERB_TABLE_HASH


SOURCE_ROOT = Path(__file__).resolve().parents[2]
INSTALLER = SOURCE_ROOT / "install/iotsploit-priv-install"
DAEMON_SOURCE = SOURCE_ROOT / "privd/iotsploit-privd"
SYSTEMD_SOURCE = SOURCE_ROOT / "systemd"
DAEMON_DESTINATION = Path("/usr/local/libexec/iotsploit-privd")
UNIT_DESTINATIONS = (
    Path("/etc/systemd/system/iotsploit-privd.socket"),
    Path("/etc/systemd/system/iotsploit-privd.service"),
)


@dataclass(frozen=True)
class NativeStatus:
    code: int
    lines: tuple[str, ...]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65_536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def install_manifest() -> tuple[tuple[Path, Path, int], ...]:
    return (
        (DAEMON_SOURCE, DAEMON_DESTINATION, 0o755),
        (SYSTEMD_SOURCE / "iotsploit-privd.socket", UNIT_DESTINATIONS[0], 0o644),
        (SYSTEMD_SOURCE / "iotsploit-privd.service", UNIT_DESTINATIONS[1], 0o644),
    )


def current_user() -> str:
    """The account this process runs as -- the one that must reach the socket."""
    return os.environ.get("SUDO_USER") or getpass.getuser()


def _service_identity(service_user: str) -> tuple[int, set[int]]:
    account = pwd.getpwnam(service_user)
    return account.pw_uid, set(os.getgrouplist(service_user, account.pw_gid))


def _writable_by(path: Path, uid: int, gids: set[int]) -> bool:
    metadata = path.stat()
    mode = stat.S_IMODE(metadata.st_mode)
    if metadata.st_uid == uid:
        return bool(mode & stat.S_IWUSR)
    if metadata.st_gid in gids:
        return bool(mode & stat.S_IWGRP)
    return bool(mode & stat.S_IWOTH)


def _permission_diagnosis(caller: str, helper_group: "grp.struct_group") -> str:
    """Say which of the two permission failures this is.

    Group membership is fixed when a session starts, so the install can have
    succeeded while the shell that ran it still cannot reach the socket. That
    reads as a failed install unless it is named.
    """
    if caller in helper_group.gr_mem and helper_group.gr_gid not in os.getgroups():
        return (
            f"{caller} is in the iotsploit group, but this session started before that "
            f"and still carries the old group set -- log out and back in, or run: newgrp iotsploit"
        )
    if caller not in helper_group.gr_mem:
        return (
            f"{caller} is not in the iotsploit group and cannot reach the socket "
            f"-- run: priv install --service-user {caller}"
        )
    return f"{caller} cannot open the helper socket: permission denied"


def _health_probe(socket_path: Path) -> tuple[str, str] | None:
    """Return None when the daemon answers correctly, else (kind, detail).

    The probe runs as the invoking account, so a permission error here is a
    statement about the caller's group membership, not about the daemon.
    """
    caller = current_user()
    request = b'{"verb":"status","args":{}}\n'
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(2)
    try:
        client.connect(os.fspath(socket_path))
        client.sendall(request)
        client.shutdown(socket.SHUT_WR)
        response = client.recv(4_096)
    except PermissionError:
        return ("permission", f"{caller} cannot open {socket_path}: permission denied")
    except OSError as exc:
        return ("unreachable", f"{caller} cannot reach {socket_path}: {exc}")
    finally:
        client.close()
    try:
        payload = json.loads(response)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ("bad-response", "daemon did not return the bounded unknown-verb response")
    answered = (
        isinstance(payload, dict)
        and payload.get("ok") is False
        and payload.get("exit") == 2
        and "unknown verb" in payload.get("stderr", "")
    )
    if answered:
        return None
    return ("bad-response", "daemon did not return the bounded unknown-verb response")


def native_status(
    service_user: str | None = None,
    *,
    socket_path: Path = DEFAULT_SOCKET_PATH,
) -> NativeStatus:
    service_user = service_user or current_user()
    destinations = (DAEMON_DESTINATION, *UNIT_DESTINATIONS)
    if not any(path.exists() or path.is_symlink() for path in (*destinations, socket_path)):
        return NativeStatus(1, ("privileged helper is not installed",))

    problems: list[str] = []
    try:
        service_uid, service_gids = _service_identity(service_user)
        helper_group = grp.getgrnam("iotsploit")
    except KeyError as exc:
        return NativeStatus(2, (f"missing account or group: {exc}",))

    for source, destination, expected_mode in install_manifest():
        try:
            metadata = destination.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                problems.append(f"{destination} is not a regular file")
                continue
            if (metadata.st_uid, metadata.st_gid) != (0, 0):
                problems.append(f"{destination} is not root:root")
            if stat.S_IMODE(metadata.st_mode) != expected_mode:
                problems.append(f"{destination} mode is not {expected_mode:04o}")
            if sha256_file(source) != sha256_file(destination):
                problems.append(f"{destination} checksum differs from packaged source")
            parent = destination.parent
            while True:
                if _writable_by(parent, service_uid, service_gids):
                    problems.append(f"{parent} is writable by {service_user}")
                if parent == parent.parent:
                    break
                parent = parent.parent
        except (FileNotFoundError, OSError) as exc:
            problems.append(f"{destination}: {exc}")

    if helper_group.gr_gid not in service_gids:
        problems.append(f"{service_user} is not a member of iotsploit")
    try:
        metadata = socket_path.lstat()
        if not stat.S_ISSOCK(metadata.st_mode):
            problems.append(f"{socket_path} is not a socket")
        if metadata.st_uid != 0 or metadata.st_gid != helper_group.gr_gid:
            problems.append(f"{socket_path} is not root:iotsploit")
        if stat.S_IMODE(metadata.st_mode) != 0o660:
            problems.append(f"{socket_path} mode is not 0660")
    except OSError as exc:
        problems.append(f"{socket_path}: {exc}")
    if not problems:
        probe_failure = _health_probe(socket_path)
        if probe_failure:
            kind, detail = probe_failure
            problems.append(
                _permission_diagnosis(current_user(), helper_group) if kind == "permission" else detail
            )

    if problems:
        return NativeStatus(2, tuple(problems))
    members = ", ".join(sorted(set(helper_group.gr_mem))) or "none"
    return NativeStatus(
        0,
        (
            "privileged helper is healthy",
            f"iotsploit group members: {members}",
            f"verb table sha256: {VERB_TABLE_HASH}",
        ),
    )


def verb_lines() -> tuple[str, ...]:
    return tuple(
        f"{verb}: {json.dumps(schema, sort_keys=True, separators=(',', ':'))}"
        for verb, schema in sorted(VERB_SCHEMAS.items())
    )
