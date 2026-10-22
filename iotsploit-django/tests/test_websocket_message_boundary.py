"""What a client may send over a socket, and what that may do to the server.

The boundary is `decoded_message`: everything a consumer treats as a message
passes through it, and nothing else in a consumer's `receive` is inside the
same try. Two separate faults were behind that rule -- json.loads raising
something other than JSONDecodeError, and a valid JSON value that is not an
object reaching a `.get()` call -- and a third that the rule prevents: a
ValueError from a consumer's own handler being reported as bad JSON.
"""

from __future__ import annotations

import os

import django
import pytest
from django.apps import apps

if not apps.ready:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
    django.setup()

from iotsploit_django.websocket.consumers_impl import (  # noqa: E402
    NotAMessage,
    decoded_message,
)

pytestmark = pytest.mark.unit


def test_an_object_is_a_message():
    assert decoded_message('{"action": "get_status"}') == {"action": "get_status"}


@pytest.mark.parametrize(
    ("text", "why"),
    [
        ("{not json", "invalid JSON"),
        ("", "invalid JSON"),
        ('{"n": ' + "9" * 8000 + "}", "invalid JSON"),   # int-string limit, a plain ValueError
        ("[" * 2000 + "]" * 2000, "invalid JSON"),       # RecursionError in the decoder
    ],
)
def test_text_that_is_not_json_is_refused_without_reaching_a_handler(text, why):
    """json.loads raises more than JSONDecodeError on text a client chooses:
    a plain ValueError past 4300 digits, a RecursionError when deeply
    nested. Both escaped and took the socket with them."""
    with pytest.raises(NotAMessage, match=why):
        decoded_message(text)


@pytest.mark.parametrize("text", ["null", "[]", '"text"', "1", "true"])
def test_valid_json_that_is_not_an_object_is_refused(text):
    """Every consumer reads its message with .get(), so these reached that
    call and raised AttributeError -- a well-formed JSON value closing a
    socket."""
    with pytest.raises(NotAMessage, match="must be a JSON object"):
        decoded_message(text)


def test_the_refusal_names_the_type_it_got():
    with pytest.raises(NotAMessage, match="not list"):
        decoded_message("[]")


def test_a_handler_s_own_value_error_is_not_a_json_error():
    """The rule the boundary exists to enforce. The parse is the only thing
    inside the try, so a ValueError raised downstream by a consumer's own
    code surfaces as itself rather than as 'invalid JSON' -- which is what a
    single wide try around parse-and-dispatch used to do."""
    message = decoded_message('{"action": "get_status"}')

    def handler(_data):
        raise ValueError("the campaign id is not a UUID")

    with pytest.raises(ValueError, match="not a UUID"):
        handler(message)
