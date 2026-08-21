"""
Interaction Port.

Defines the stable interface a running plugin uses to ask the operator a
question and wait for a typed answer.

The port is deliberately small: four methods, one per real capability. Plugin
ergonomics live in :class:`PromptSugar`, a concrete mixin written purely in
terms of those four, so an adapter implements four methods rather than sixteen.

Nothing in this module knows about Django, Celery, HTTP, or a terminal. See
``docs/interactive_exploit_plugin_plan.md`` Appendix A.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol, Sequence, runtime_checkable

# A `secret` kind is deliberately absent from v1 -- see plan decision 7.
PROMPT_KINDS = (
    "confirm",
    "text",
    "integer",
    "single_choice",
    "multiple_choice",
)

DEFAULT_TIMEOUT = 300.0


class InteractionError(Exception):
    """Base class for every interaction failure."""


class InteractionUnavailable(InteractionError):
    """No interaction broker is bound to the current execution."""


class InteractionTimeout(InteractionError):
    """The operator did not answer before the prompt expired."""


class InteractionCancelled(InteractionError):
    """The execution was cancelled while a prompt was open."""


class InteractionInvalid(InteractionError):
    """The plugin used the port incorrectly (a bug, not an operator condition)."""


@dataclass(frozen=True)
class Choice:
    """One selectable option in a choice prompt."""

    value: str
    label: str | None = None

    @property
    def display(self) -> str:
        return self.label if self.label is not None else self.value


@dataclass(frozen=True)
class Prompt:
    """A typed question for the operator.

    Validated on construction: a malformed prompt is a bug in the plugin, so it
    raises :class:`InteractionInvalid` before anything is persisted or shown.
    """

    kind: str
    title: str
    description: str | None = None
    default: Any = None
    timeout: float = DEFAULT_TIMEOUT
    choices: tuple[Choice, ...] = field(default_factory=tuple)
    required: bool = True
    min_value: int | None = None       # integer
    max_value: int | None = None       # integer
    max_length: int | None = None      # text
    min_selected: int | None = None    # multiple_choice
    confirm_label: str = "Confirm"     # confirm
    deny_label: str = "Cancel"         # confirm

    def __post_init__(self):
        object.__setattr__(self, "choices", normalize_choices(self.choices))
        self._validate()

    def _validate(self) -> None:
        if self.kind not in PROMPT_KINDS:
            raise InteractionInvalid(
                f"Unknown prompt kind {self.kind!r}. Expected one of: "
                f"{', '.join(PROMPT_KINDS)}."
            )
        if not str(self.title).strip():
            raise InteractionInvalid("A prompt needs a title.")
        if self.timeout <= 0:
            raise InteractionInvalid(
                f"timeout must be positive, got {self.timeout!r}."
            )

        if self.kind in ("single_choice", "multiple_choice"):
            if not self.choices:
                raise InteractionInvalid(
                    f"A {self.kind} prompt needs at least one choice."
                )
            values = [c.value for c in self.choices]
            if len(set(values)) != len(values):
                raise InteractionInvalid("Choice values must be unique.")

        if self.kind == "integer" and None not in (self.min_value, self.max_value):
            if self.min_value > self.max_value:
                raise InteractionInvalid(
                    f"min_value {self.min_value} is above max_value {self.max_value}."
                )

        if self.kind == "multiple_choice" and self.min_selected is not None:
            if self.min_selected < 0 or self.min_selected > len(self.choices):
                raise InteractionInvalid(
                    f"min_selected {self.min_selected} is out of range for "
                    f"{len(self.choices)} choices."
                )

        if self.default is not None:
            try:
                coerce_answer(self, self.default)
            except InteractionInvalid as exc:
                raise InteractionInvalid(f"Invalid default: {exc}") from None

    @property
    def choice_values(self) -> list[str]:
        return [c.value for c in self.choices]

    def validation_schema(self) -> dict[str, Any]:
        """The constraint description sent to clients (plan A.5).

        Absent keys mean unconstrained. Transport envelopes are assembled by
        the adapter; this is only the domain part.
        """
        if self.kind == "confirm":
            return {
                "confirm_label": self.confirm_label,
                "deny_label": self.deny_label,
            }
        if self.kind == "text":
            schema: dict[str, Any] = {"required": self.required}
            if self.max_length is not None:
                schema["max_length"] = self.max_length
            return schema
        if self.kind == "integer":
            schema = {"required": self.required}
            if self.min_value is not None:
                schema["min"] = self.min_value
            if self.max_value is not None:
                schema["max"] = self.max_value
            return schema
        if self.kind == "single_choice":
            return {
                "required": self.required,
                "choices": [
                    {"value": c.value, "label": c.display} for c in self.choices
                ],
            }
        # multiple_choice
        schema = {
            "choices": [{"value": c.value, "label": c.display} for c in self.choices]
        }
        if self.min_selected is not None:
            schema["min_selected"] = self.min_selected
        return schema


def normalize_choices(choices: Iterable[Any] | None) -> tuple[Choice, ...]:
    """Accept strings, (value, label) pairs, dicts, or Choice objects."""
    if not choices:
        return ()
    out: list[Choice] = []
    for item in choices:
        if isinstance(item, Choice):
            out.append(item)
        elif isinstance(item, str):
            out.append(Choice(item))
        elif isinstance(item, dict):
            out.append(Choice(str(item["value"]), item.get("label")))
        elif isinstance(item, (tuple, list)) and len(item) == 2:
            out.append(Choice(str(item[0]), str(item[1])))
        else:
            raise InteractionInvalid(f"Cannot read {item!r} as a choice.")
    return tuple(out)


def coerce_answer(prompt: Prompt, value: Any) -> Any:
    """Validate a raw answer against the prompt and return the typed value.

    Shared by every adapter and by the Django answer endpoint so the three
    cannot drift. Raises :class:`InteractionInvalid` describing what is wrong.
    """
    kind = prompt.kind

    if kind == "confirm":
        if isinstance(value, bool):
            return value
        raise InteractionInvalid("Expected true or false.")

    if kind == "text":
        if value is None:
            value = ""
        if not isinstance(value, str):
            raise InteractionInvalid("Expected text.")
        if prompt.required and not value.strip():
            raise InteractionInvalid("This answer is required.")
        if prompt.max_length is not None and len(value) > prompt.max_length:
            raise InteractionInvalid(
                f"At most {prompt.max_length} characters; got {len(value)}."
            )
        return value

    if kind == "integer":
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise InteractionInvalid("Expected a whole number.")
        try:
            number = int(str(value).strip())
        except (TypeError, ValueError):
            raise InteractionInvalid(f"{value!r} is not a whole number.") from None
        if prompt.min_value is not None and number < prompt.min_value:
            raise InteractionInvalid(f"Must be at least {prompt.min_value}.")
        if prompt.max_value is not None and number > prompt.max_value:
            raise InteractionInvalid(f"Must be at most {prompt.max_value}.")
        return number

    if kind == "single_choice":
        if not isinstance(value, str):
            raise InteractionInvalid("Expected one choice value.")
        if value not in prompt.choice_values:
            raise InteractionInvalid(
                f"{value!r} is not one of: {', '.join(prompt.choice_values)}."
            )
        return value

    # multiple_choice
    if isinstance(value, str) or not isinstance(value, (list, tuple, set)):
        raise InteractionInvalid("Expected a list of choice values.")
    selected = list(dict.fromkeys(value))
    for item in selected:
        if item not in prompt.choice_values:
            raise InteractionInvalid(
                f"{item!r} is not one of: {', '.join(prompt.choice_values)}."
            )
    minimum = prompt.min_selected
    if minimum is not None and len(selected) < minimum:
        raise InteractionInvalid(f"Select at least {minimum}.")
    return selected


def guard_sync_call(method: str) -> None:
    """Refuse a blocking call made from inside a running event loop.

    ``run_plugin_in_process`` drives ``execute_async`` through
    ``loop.run_until_complete``. A blocking ``request()`` there would stall that
    loop and deadlock the run, so fail loudly at the first call instead.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return
    raise InteractionInvalid(
        f"{method}() blocks and was called from async code. "
        f"Use a{method}() inside execute_async()."
    )


@runtime_checkable
class InteractionPort(Protocol):
    """The entire port. Everything else is built from these four methods."""

    def request(self, prompt: Prompt) -> Any: ...

    async def arequest(self, prompt: Prompt) -> Any: ...

    def check_cancelled(self) -> None: ...

    async def acheck_cancelled(self) -> None: ...


class PromptSugar:
    """Typed convenience wrappers, shared by every adapter.

    Concrete and implemented purely against ``request`` / ``arequest``, so it
    stays out of the port and adapters inherit it for free.
    """

    def request_kw(self, **kwargs: Any) -> Any:
        return self.request(Prompt(**kwargs))  # type: ignore[attr-defined]

    async def arequest_kw(self, **kwargs: Any) -> Any:
        return await self.arequest(Prompt(**kwargs))  # type: ignore[attr-defined]

    # -- confirm ---------------------------------------------------------
    def confirm(self, title: str, description: str | None = None, **kw: Any) -> bool:
        return self.request_kw(
            kind="confirm", title=title, description=description, **kw
        )

    async def aconfirm(
        self, title: str, description: str | None = None, **kw: Any
    ) -> bool:
        return await self.arequest_kw(
            kind="confirm", title=title, description=description, **kw
        )

    # -- text ------------------------------------------------------------
    def text(self, title: str, **kw: Any) -> str:
        return self.request_kw(kind="text", title=title, **kw)

    async def atext(self, title: str, **kw: Any) -> str:
        return await self.arequest_kw(kind="text", title=title, **kw)

    # -- integer ---------------------------------------------------------
    def integer(self, title: str, **kw: Any) -> int:
        return self.request_kw(kind="integer", title=title, **kw)

    async def ainteger(self, title: str, **kw: Any) -> int:
        return await self.arequest_kw(kind="integer", title=title, **kw)

    # -- single_choice ---------------------------------------------------
    def choose(self, title: str, choices: Sequence[Any], **kw: Any) -> str:
        return self.request_kw(
            kind="single_choice", title=title, choices=choices, **kw
        )

    async def achoose(self, title: str, choices: Sequence[Any], **kw: Any) -> str:
        return await self.arequest_kw(
            kind="single_choice", title=title, choices=choices, **kw
        )

    # -- multiple_choice -------------------------------------------------
    def choose_many(
        self, title: str, choices: Sequence[Any], *, min_selected: int = 1, **kw: Any
    ) -> list[str]:
        return self.request_kw(
            kind="multiple_choice",
            title=title,
            choices=choices,
            min_selected=min_selected,
            **kw,
        )

    async def achoose_many(
        self, title: str, choices: Sequence[Any], *, min_selected: int = 1, **kw: Any
    ) -> list[str]:
        return await self.arequest_kw(
            kind="multiple_choice",
            title=title,
            choices=choices,
            min_selected=min_selected,
            **kw,
        )
