"""The canonical string form of a CAN frame id.

This is a join key. Reconciliation compares an observation's ``subject_id``
against what the catalog stores, and a mismatch does not raise -- it matches
nothing and reads as "never heard of this frame". So the form is pinned by
tests rather than left to each call site.
"""

from __future__ import annotations

import os

import django
import pytest
from django.apps import apps

if not apps.ready:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
    django.setup()

from iotsploit_django.tools.can_facet import canonical_frame_id  # noqa: E402

pytestmark = pytest.mark.unit


def test_a_standard_id_is_three_uppercase_hex_digits():
    assert canonical_frame_id(0x0A0) == "0A0"
    assert canonical_frame_id(0x65C) == "65C"
    assert canonical_frame_id(0x7FF) == "7FF"


def test_an_extended_id_is_eight():
    assert canonical_frame_id(0x17F00015, is_extended=True) == "17F00015"


def test_the_same_number_reads_differently_in_each_id_space():
    """A standard 0x123 and an extended 0x123 are different frames on one
    wire. Padding to the width of the space is what keeps them apart."""
    assert canonical_frame_id(0x123) != canonical_frame_id(0x123, is_extended=True)


def test_there_is_no_0x_and_no_lowercase():
    key = canonical_frame_id(0x1AB)

    assert not key.startswith("0x")
    assert key == key.upper()


def test_a_small_id_is_padded_rather_than_left_short():
    """Otherwise 0x40 sorts and joins differently from 040."""
    assert canonical_frame_id(0x40) == "040"
    assert canonical_frame_id(0x5, is_extended=True) == "00000005"
