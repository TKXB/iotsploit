"""Thin assistant socket adapter. Execution outlives individual connections."""

import uuid
import json

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.core.exceptions import ObjectDoesNotExist

from iotsploit_django.agent_runtime import store
from iotsploit_django.agent_runtime.runtime import runtime


class AIAssistantConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        value = self.scope["url_route"]["kwargs"]["session_id"]
        try:
            self.client_key = uuid.UUID(value).hex
        except ValueError:
            await self.close(code=4400)
            return
        self.selected = None
        await self.accept()
        await self.send_json(await runtime.discover())
        await self.send_sessions()

    async def disconnect(self, close_code):
        self.unsubscribe()

    def unsubscribe(self):
        if getattr(self, "selected", None):
            runtime.listeners.get(self.selected, set()).discard(self.send_json)

    async def send_sessions(self):
        await self.send_json({"type": "sessions", "sessions": await store.sessions(self.client_key)})

    async def select(self, session_id, after=0):
        session = await store.load(self.client_key, session_id)
        self.unsubscribe()
        self.selected = str(session.id)
        runtime.listeners.setdefault(self.selected, set()).add(self.send_json)
        last = await store.last_event(session.id)
        if (
            last
            and self.selected not in runtime.active
            and last["type"] not in {"turn.done", "turn.error", "turn.cancelled"}
        ):
            await runtime.emit(
                session.id,
                last["turn_id"],
                "turn.error",
                {"message": "The server stopped during this turn. It was not rerun. Send a new message to continue."},
            )
        events = await store.events(session.id, after)
        await self.send_json(
            {
                "type": "session.loaded",
                "session": store.summary(session),
                "events": events,
                "running": self.selected in runtime.active,
            }
        )
        return session

    async def receive(self, text_data=None, bytes_data=None, **kwargs):
        try:
            data = json.loads(text_data)
        except (ValueError, TypeError, RecursionError):
            await self.send_json({"type": "error", "message": "Invalid JSON assistant command"})
            return
        await self.receive_json(data)

    async def receive_json(self, data, **kwargs):
        try:
            if not isinstance(data, dict):
                raise ValueError("Expected an assistant command object")
            kind = data.get("type")
            if kind == "discovery.refresh":
                manual = data.get("manual")
                if manual is not None and (
                    not isinstance(manual, dict)
                    or manual.get("engine") not in {"claude", "codex", "opencode"}
                    or not isinstance(manual.get("path"), str)
                ):
                    raise ValueError("Specify an agent engine and executable path")
                await self.send_json(await runtime.discover(manual, refresh=True))
            elif kind == "session.list":
                await self.send_sessions()
            elif kind == "session.create":
                session = await runtime.create(self.client_key, data)
                await self.send_sessions()
                await self.select(session["id"])
            elif kind == "session.load":
                await self.select(data["session_id"], max(0, int(data.get("after", 0))))
            elif kind in {"turn.send", "quick_action.run", "turn.cancel"}:
                session = await store.load(self.client_key, data["session_id"])
                if kind == "turn.cancel":
                    await runtime.cancel(session.id)
                else:
                    await runtime.start(session, data)
            else:
                raise ValueError("Unknown assistant command")
        except (ValueError, TypeError, KeyError, ObjectDoesNotExist) as exc:
            message = "Conversation not found" if isinstance(exc, ObjectDoesNotExist) else str(exc)
            await self.send_json({"type": "error", "message": message, "running": self.selected in runtime.active})
