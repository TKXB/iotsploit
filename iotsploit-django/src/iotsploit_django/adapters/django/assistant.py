"""Durable assistant conversations; runtime processes remain process-local."""

import uuid

from django.db import models


class AssistantSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client_key = models.CharField(max_length=64, db_index=True)
    mode = models.CharField(max_length=16, default="api")
    engine = models.CharField(max_length=16, blank=True)
    binary_path = models.TextField(blank=True)
    config_id = models.PositiveIntegerField(null=True, blank=True)
    native_session_id = models.TextField(blank=True)
    title = models.CharField(max_length=120, default="New conversation")
    history = models.JSONField(default=list)
    next_seq = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)


class AssistantEvent(models.Model):
    session = models.ForeignKey(AssistantSession, on_delete=models.CASCADE, related_name="events")
    turn_id = models.UUIDField()
    seq = models.PositiveIntegerField()
    type = models.CharField(max_length=32)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["seq"]
        constraints = [models.UniqueConstraint(fields=["session", "seq"], name="assistant_event_sequence")]
