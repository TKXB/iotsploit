"""
SQLAlchemy ORM mappings for Target domain (adapter layer).
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Type

from sqlalchemy import Column, JSON, String

from iotsploit_django.adapters.django.sqlalchemy_database import get_default_sqlalchemy_db
from iotsploit_core.domain.target import ComponentFactory, GenericTarget, Target, Vehicle
from iotsploit_django.tools.xlogger import xlog

_db = get_default_sqlalchemy_db()
Base = _db.Base
engine = _db.engine
SessionLocal = _db.SessionLocal


class TargetDBModel(Base):
    __tablename__ = "targets"

    target_id = Column(String, primary_key=True)
    name = Column(String)
    type = Column(String)
    status = Column(String)
    properties = Column(JSON)
    ip_address = Column(String, nullable=True)
    location = Column(String, nullable=True)
    components = Column(JSON, nullable=True)
    interfaces = Column(JSON, nullable=True)

    __mapper_args__ = {"polymorphic_on": type, "polymorphic_identity": "target"}

    def __init__(self, target: Target):
        self.target_id = target.target_id
        self.name = target.name
        self.type = target.type
        self.status = target.status
        self.properties = target.properties


class VehicleDBModel(TargetDBModel):
    __mapper_args__ = {"polymorphic_identity": "vehicle"}

    def __init__(self, target: Vehicle):
        super().__init__(target)
        self.ip_address = target.ip_address
        self.location = target.location
        self.components = [comp.model_dump() for comp in target.components]
        self.interfaces = [intf.model_dump() for intf in target.interfaces]


class TargetManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TargetManager, cls).__new__(cls)
            cls._instance.initialize()
        return cls._instance

    def initialize(self):
        self.targets: Dict[str, Type[Target]] = {}
        Base.metadata.create_all(engine)
        self.Session = SessionLocal
        self.current_target: Optional[Target] = None

    @classmethod
    def get_instance(cls):
        return cls()

    def register_target(self, target_type: str, target_class: Type[Target]):
        self.targets[target_type] = target_class

    def create_target(self, target_type: str, **kwargs) -> Target:
        if target_type in self.targets:
            target_class = self.targets[target_type]
            target = target_class(**kwargs)
            self.save_target(target)
            return target
        raise ValueError(f"No target type registered for: {target_type}")

    def save_target(self, target: Target):
        session = self.Session()
        try:
            existing_target = session.query(TargetDBModel).filter_by(target_id=target.target_id).first()
            if existing_target:
                existing_target.name = target.name
                existing_target.status = target.status
                existing_target.properties = target.properties

                if isinstance(target, Vehicle):
                    existing_target.ip_address = target.ip_address
                    existing_target.location = target.location
                    existing_target.components = [comp.model_dump() for comp in target.components]
                    existing_target.interfaces = [intf.model_dump() for intf in target.interfaces]

                session.commit()
            else:
                if isinstance(target, Vehicle):
                    target_model = VehicleDBModel(target)
                else:
                    target_model = TargetDBModel(target)
                session.add(target_model)
                session.commit()
        except Exception as e:
            session.rollback()
            xlog.error(f"An error occurred while saving target '{target.target_id}': {e}", name="target_model")
            raise
        finally:
            session.close()

    def get_all_targets(self) -> List[Dict[str, Any]]:
        session = self.Session()
        try:
            targets = session.query(TargetDBModel).all()
            result = []
            for t in targets:
                target_info: Dict[str, Any] = {
                    "target_id": t.target_id,
                    "name": t.name,
                    "type": t.type,
                    "status": t.status,
                    "properties": t.properties,
                }
                if isinstance(t, VehicleDBModel):
                    target_info["ip_address"] = t.ip_address
                    target_info["location"] = t.location
                    target_info["components"] = t.components
                    target_info["interfaces"] = t.interfaces
                result.append(target_info)
            return result
        finally:
            session.close()

    # ---------------- current target (in-memory) ----------------

    def get_current_target(self) -> Optional[Target]:
        return self.current_target

    def set_current_target(self, target: Target) -> None:
        self.current_target = target

    # ---------------- hydrate / update helpers ----------------

    def create_target_instance(self, target_data: Dict[str, Any]) -> Target:
        """
        Create a domain Target instance from a dict (as returned by get_all_targets or request payloads).
        """
        target_type = target_data.get("type", "vehicle")

        # Re-hydrate components/interfaces using the domain factory when possible
        raw_components = target_data.get("components") or []
        components = []
        for c in raw_components:
            if isinstance(c, dict):
                components.append(ComponentFactory.create_component(c))
            else:
                # already a pydantic model
                components.append(c)

        interfaces = target_data.get("interfaces") or []

        common_kwargs: Dict[str, Any] = {
            "target_id": target_data.get("target_id", ""),
            "name": target_data.get("name", ""),
            "type": target_type,
            "status": target_data.get("status", "active"),
            "properties": target_data.get("properties", {}) or {},
        }

        if target_type == "vehicle":
            return Vehicle(
                **common_kwargs,
                ip_address=target_data.get("ip_address"),
                location=target_data.get("location"),
                components=components,
                interfaces=interfaces,
            )

        return GenericTarget(**common_kwargs)

    def update_target(self, target_data: Dict[str, Any]) -> bool:
        """
        Update a target from dict payload. Returns success flag.
        """
        try:
            target_instance = self.create_target_instance(target_data)
            self.save_target(target_instance)
            # keep current_target in sync if it's the same target
            if self.current_target and getattr(self.current_target, "target_id", None) == target_instance.target_id:
                self.current_target = target_instance
            return True
        except Exception as e:
            xlog.error(f"update_target failed: {e}", name="target_model")
            return False

    def parse_and_set_target_from_json(self, json_file_path: str):
        xlog.debug(f"Reading JSON file from: {json_file_path}", name="target_model")
        if not os.path.exists(json_file_path):
            xlog.error(f"File not found: {json_file_path}", name="target_model")
            return

        with open(json_file_path, "r") as file:
            data = json.load(file)

        imported_count = 0
        for target in data.get("targets", []):
            target_type = target.get("type", "vehicle")
            target_class = self.targets.get(target_type, Vehicle)

            # Re-hydrate components/interfaces using the domain factory
            components = [ComponentFactory.create_component(c) for c in target.get("components", [])]
            interfaces = target.get("interfaces", [])

            target_instance = target_class(
                target_id=target.get("target_id", ""),
                name=target.get("name", ""),
                type=target_type,
                status=target.get("status", "active"),
                properties=target.get("properties", {}),
                ip_address=target.get("ip_address"),
                location=target.get("location"),
                components=components,
                interfaces=interfaces,
            )
            self.save_target(target_instance)
            self.current_target = target_instance
            imported_count += 1

        xlog.info(f"Imported {imported_count} targets from JSON file: {json_file_path}", name="target_model")


