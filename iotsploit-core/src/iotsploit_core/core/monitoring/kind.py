"""Monitor kinds: the plugins that each add one kind of target monitor.

A kind describes its settings with the parameter schema exploit plugins use
(``type``, ``required``, ``default``, ``description``, ``validation``), so a
client builds the form from :meth:`MonitorKind.describe` and never needs to know
the kind. ``resource`` and ``target`` are plan-entry fields; every other
parameter is an entry option.

A parameter may declare ``"depends_on": ["resource"]``: its choices come from
what the kind finds once those values are chosen (the chip on a probe). A
client collects the depended-on values first, then asks for the rest with
:meth:`MonitorKind.describe` given those values.

Kinds come from the ``iotsploit.monitors`` entry-point group and, optionally,
from ``.py`` files in a monitor plugins directory.
"""

from __future__ import annotations

import importlib.util
import logging
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Callable, Mapping

from iotsploit_core.core.monitoring.source import MonitorPlanEntry, MonitorSource

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "iotsploit.monitors"
DISPLAY_TYPES = ("text", "hex", "json")
"""How a client may render a field of an observation's ``detail``."""


@dataclass(frozen=True)
class MonitorContext:
    """What the application lends a kind."""

    driver_classes: Callable[[], Mapping[str, type]]
    """Loaded device driver classes by name; a kind builds its own instances."""


class MonitorKind:
    KIND = ""
    NAME = ""
    DESCRIPTION = ""
    DISPLAY: Mapping[str, str] = {}
    """``detail`` field -> one of :data:`DISPLAY_TYPES`; unlisted fields are ``text``."""

    def __init__(self, context: MonitorContext):
        self.context = context

    def parameters(self, values: Mapping) -> dict:
        """The settings schema, given the values chosen so far (empty at first).

        Called per request, so choices may be live. The composition root holds
        the lease on ``values["resource"]`` while this runs, so a kind may open it.
        """
        return {}

    def validate(self, entry: MonitorPlanEntry) -> None:
        """Raise ``ValueError`` for an entry that cannot work, before any hardware opens."""

    def create(self, entry: MonitorPlanEntry) -> MonitorSource:
        raise NotImplementedError

    def policy(self, source: MonitorSource):
        """The campaign policy for an open source; None selects the default health policy."""
        return None

    def describe(self, values: Mapping | None = None) -> dict:
        return {
            "kind": self.KIND,
            "name": self.NAME or self.KIND,
            "description": self.DESCRIPTION,
            "parameters": self.parameters(values or {}),
            "display": dict(self.DISPLAY),
        }


def load_monitor_kinds(context: MonitorContext, plugins_dir: str | Path | None = None) -> list[MonitorKind]:
    """Every loadable kind; a plugin that fails to load is logged and skipped."""
    classes: dict[str, type] = {}

    def add(cls, origin: str) -> None:
        if not (isinstance(cls, type) and issubclass(cls, MonitorKind) and cls.KIND):
            logger.warning("Ignoring %s: not a MonitorKind with a KIND", origin)
        elif cls.KIND in classes:
            logger.warning("Ignoring %s: monitor kind %r is already loaded", origin, cls.KIND)
        else:
            classes[cls.KIND] = cls

    for entry_point in metadata.entry_points(group=ENTRY_POINT_GROUP):
        try:
            add(entry_point.load(), entry_point.value)
        except Exception as exc:
            logger.error("Failed to load monitor kind %s: %s", entry_point.value, exc)

    if plugins_dir is not None:
        for path in sorted(Path(plugins_dir).glob("*.py")):
            try:
                spec = importlib.util.spec_from_file_location(f"iotsploit_monitor_{path.stem}", path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
            except Exception as exc:
                logger.error("Failed to load monitor plugin %s: %s", path, exc)
                continue
            for value in vars(module).values():
                # Only classes the file defines: an imported base is not its plugin.
                if (isinstance(value, type) and issubclass(value, MonitorKind)
                        and value.__module__ == module.__name__):
                    add(value, str(path))

    kinds = []
    for cls in classes.values():
        try:
            kinds.append(cls(context))
        except Exception as exc:
            logger.error("Failed to start monitor kind %s: %s", cls.KIND, exc)
    return kinds
