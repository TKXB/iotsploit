"""Database access runs off the ASGI event loop."""

from channels.db import database_sync_to_async
from django.db import transaction
from django.db.models import F
from django.utils import timezone
import uuid

from iotsploit_django.adapters.django.assistant import AssistantEvent, AssistantSession
from iotsploit_django.models.AIModel_Model import AIModelConfig


def summary(session):
    return {
        **{key: str(getattr(session, key)) for key in ("id", "mode", "engine", "title", "binary_path")},
        "config_id": session.config_id,
    }


@database_sync_to_async
def sessions(client_key):
    return [summary(s) for s in AssistantSession.objects.filter(client_key=client_key).order_by("-created_at")[:100]]


@database_sync_to_async
def create(client_key, **fields):
    return summary(AssistantSession.objects.create(client_key=client_key, **fields))


@database_sync_to_async
def load(client_key, session_id):
    return AssistantSession.objects.get(client_key=client_key, id=uuid.UUID(str(session_id)))


def event_dict(event):
    return {
        "type": event.type,
        "session_id": str(event.session_id),
        "turn_id": str(event.turn_id),
        "seq": event.seq,
        "created_at": event.created_at.isoformat(),
        **event.payload,
    }


@database_sync_to_async
def events(session_id, after=0):
    return [event_dict(e) for e in AssistantEvent.objects.filter(session_id=session_id, seq__gt=after)]


@database_sync_to_async
def last_event(session_id):
    event = AssistantEvent.objects.filter(session_id=session_id).order_by("-seq").first()
    return event_dict(event) if event else None


@database_sync_to_async
def has_turn(session_id, turn_id):
    return AssistantEvent.objects.filter(session_id=session_id, turn_id=turn_id).exists()


@database_sync_to_async
def append(session_id, turn_id, kind, payload):
    with transaction.atomic():
        session = AssistantSession.objects.select_for_update().get(id=session_id)
        session.next_seq += 1
        session.save(update_fields=["next_seq"])
        return event_dict(
            AssistantEvent.objects.create(
                session=session, turn_id=turn_id, seq=session.next_seq, type=kind, payload=payload
            )
        )


@database_sync_to_async
def save_context(session):
    session.save(update_fields=["history", "native_session_id", "title", "config_id"])


@database_sync_to_async
def configs():
    return list(
        AIModelConfig.objects.filter(is_active=True).values("id", "name", "provider", "model_name", "is_default")
    )


@database_sync_to_async
def record_usage(config_id):
    AIModelConfig.objects.filter(id=config_id).update(usage_count=F("usage_count") + 1, last_used_at=timezone.now())


@database_sync_to_async
def config(config_id, *, required=True):
    query = AIModelConfig.objects.filter(is_active=True)
    result = query.filter(id=config_id).first() if config_id else query.filter(is_default=True).first()
    if result is None and required:
        raise ValueError("Choose an active API configuration in Model settings.")
    return result
