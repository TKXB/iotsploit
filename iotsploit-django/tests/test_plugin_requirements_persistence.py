"""What the plugin repository is allowed to persist, and what it must not.

The invariant: `requirements` is a static property of a plugin -- the same on
every host -- so it belongs in the database. *Availability* is the answer to
"are those requirements met here", which is true of one machine at one moment.
Django, the MCP server and a Celery worker can be three different hosts, so a
persisted availability would be one node's answer served to all of them.

Concretely, the failure this guards against: a Linux Django writes
"socketcan: available", a Windows worker reads it back, and the run is
authorised on a machine that has no SocketCAN. The executor re-resolves before
running for exactly this reason, but the cheapest defence is never storing the
field at all -- so this test fails the moment an availability-shaped column
appears on the model.
"""

from __future__ import annotations

import os

import django
import pytest
from django.apps import apps

if not apps.ready:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
    django.setup()

from iotsploit_core.domain.plugin import PluginMeta  # noqa: E402
from iotsploit_django.adapters.django.plugins.models import Plugin  # noqa: E402
from iotsploit_django.adapters.django.plugins.repos import DjangoPluginMetaRepository  # noqa: E402

pytestmark = [pytest.mark.django, pytest.mark.contract]


AVAILABILITY_FIELDS = ("available", "availability", "unavailable_reason", "reason", "hint")


def test_requirements_survive_a_repository_round_trip(db):
    repo = DjangoPluginMetaRepository()
    meta = PluginMeta(
        name="can_live_capture",
        module_path="iotsploit_exploits.canbus.live_capture:CanLiveCapturePlugin",
        description="Capture CAN frames",
        requirements=("socketcan", "priv-helper"),
    )

    repo.upsert(meta)
    stored = {m.name: m for m in repo.list_enabled()}

    assert stored["can_live_capture"].requirements == ("socketcan", "priv-helper")


def test_requirements_are_replaced_not_merged_when_a_plugin_changes(db):
    """A plugin that drops a requirement must not keep it from the last scan."""
    repo = DjangoPluginMetaRepository()
    name = "nmap_scan"
    base = dict(name=name, module_path="iotsploit_exploits.nmap_scan.nmap_scan:NmapScanPlugin")

    repo.upsert(PluginMeta(**base, requirements=("nmap", "priv-helper")))
    repo.upsert(PluginMeta(**base, requirements=("nmap",)))

    stored = {m.name: m for m in repo.list_enabled()}
    assert stored[name].requirements == ("nmap",)


def test_a_plugin_with_no_requirements_round_trips_as_an_empty_tuple(db):
    repo = DjangoPluginMetaRepository()
    repo.upsert(
        PluginMeta(
            name="async_sleep_attack",
            module_path="iotsploit_exploits.demo.async_sleep_attack:AsyncSleepAttackPlugin",
        )
    )

    stored = {m.name: m for m in repo.list_enabled()}
    assert stored["async_sleep_attack"].requirements == ()


def test_plugin_meta_carries_requirements_and_no_availability():
    """The domain type is the contract the repository serializes."""
    fields = set(PluginMeta.__dataclass_fields__)

    assert "requirements" in fields
    assert not fields & set(AVAILABILITY_FIELDS)


def test_the_plugin_table_has_no_column_for_availability():
    """Availability is per-host, so it must never reach the database.

    Checked against the model rather than a migration so that adding the field
    fails here even before a migration is generated for it.
    """
    columns = {field.name for field in Plugin._meta.get_fields()}

    assert "requirements" in columns
    assert not columns & set(AVAILABILITY_FIELDS)
