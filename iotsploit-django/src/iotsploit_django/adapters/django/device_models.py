"""
SQLAlchemy ORM mapping for device driver on/off state (adapter layer).

Kept under Django adapters because runtime wiring currently uses Django settings to locate DB.
"""

from __future__ import annotations

import datetime

from sqlalchemy import Boolean, Column, DateTime, String

from iotsploit_django.adapters.django.sqlalchemy_database import get_default_sqlalchemy_db

_db = get_default_sqlalchemy_db()
Base = _db.Base
engine = _db.engine
SessionLocal = _db.SessionLocal


class DeviceDriverState(Base):
    __tablename__ = "device_driver_states"

    driver_name = Column(String, primary_key=True)
    enabled = Column(Boolean, default=True)
    description = Column(String, nullable=True)
    last_updated = Column(DateTime, default=lambda: datetime.datetime.now())

    def __init__(self, driver_name, enabled=True, description=None):
        self.driver_name = driver_name
        self.enabled = enabled
        self.description = description
        self.last_updated = datetime.datetime.now()

    def to_dict(self):
        return {
            "driver_name": self.driver_name,
            "enabled": self.enabled,
            "description": self.description,
            "last_updated": str(self.last_updated),
        }

