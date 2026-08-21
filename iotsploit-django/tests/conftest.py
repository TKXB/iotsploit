"""Opt-in hermetic database for Django ORM tests.

The testing policy excludes tests needing a manually provisioned service
"until those dependencies are made hermetic". This is that step for the ORM: a
throwaway database built from the migrations, with every test rolled back, so
nothing touches the developer's `db.sqlite3`. For SQLite it resolves to
`:memory:` and never reaches the filesystem.

Nothing here runs at import time. This module is imported during collection,
before any test, so calling `django.setup()` at module scope would pull the app
registry up earlier than the test modules do and reorder global registrations
that resolve by import order -- which silently breaks the facet tests. The
fixtures below are opt-in: a test that does not ask for `db` is unaffected by
this file.

pytest-django would provide the same thing, but it is not a dependency of this
project and this is small enough not to need one.
"""

from __future__ import annotations

import os

import pytest


def _ensure_django():
    """Set Django up, matching how the test modules do it themselves."""
    import django
    from django.apps import apps

    if not apps.ready:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
        django.setup()


@pytest.fixture(scope="session")
def django_test_database():
    """Build a throwaway database for the session and tear it down after."""
    _ensure_django()

    from django.db import connection
    from django.test.utils import setup_test_environment, teardown_test_environment

    setup_test_environment()
    old_config = connection.creation.create_test_db(verbosity=0, autoclobber=True)
    try:
        yield connection
    finally:
        connection.creation.destroy_test_db(old_config, verbosity=0)
        teardown_test_environment()


@pytest.fixture
def db(django_test_database):
    """A database that forgets everything this test did.

    Request it from any test that touches the ORM.
    """
    from django.db import transaction

    atomic = transaction.atomic()
    atomic.__enter__()
    try:
        yield django_test_database
    finally:
        transaction.set_rollback(True)
        atomic.__exit__(None, None, None)
