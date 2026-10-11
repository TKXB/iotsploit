"""A driver switched off stays off on a database nothing else has touched.

The repository used to create its table through a Base of its own, which holds
no models, so the table only existed if the old device-table code had run
first. Without it every write failed quietly and every read said "enabled":
the UI showed a disabled driver as on.
"""

from __future__ import annotations

import os

import django
import pytest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
django.setup()

from iotsploit_django.adapters.django import driver_state_repo  # noqa: E402
from iotsploit_django.adapters.django.driver_state_repo import DjangoDriverStateRepository  # noqa: E402
from iotsploit_django.adapters.sqlalchemy.database import create_sqlalchemy_db  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture
def repo(monkeypatch, tmp_path):
    monkeypatch.setattr(
        driver_state_repo,
        "get_default_sqlalchemy_db",
        lambda: create_sqlalchemy_db(f"sqlite:///{tmp_path / 'fresh.sqlite3'}"),
    )
    return DjangoDriverStateRepository()


def test_a_disabled_driver_reads_back_disabled_on_a_fresh_database(repo):
    repo.set_enabled("drv_stlink", False, description="bench rig has no ST-Link")

    assert repo.list_enabled() == {"drv_stlink": False}
    assert repo.get_enabled("drv_stlink") is False


def test_enabling_again_replaces_the_saved_state(repo):
    repo.set_enabled("drv_stlink", False)
    repo.set_enabled("drv_stlink", True)

    assert repo.list_enabled() == {"drv_stlink": True}


def test_a_driver_never_saved_has_no_state(repo):
    assert repo.get_enabled("drv_jlink") is None
    assert repo.list_enabled() == {}
