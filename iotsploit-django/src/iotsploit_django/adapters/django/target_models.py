"""
SQLAlchemy ORM mappings for Target domain (adapter layer).
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Type

from sqlalchemy import Column, JSON, String, DateTime, text as sqlalchemy_text
from sqlalchemy.sql import func

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
    created_at = Column(DateTime, default=func.now(), nullable=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=True)

    def __init__(self, target: Target):
        self.target_id = target.target_id
        self.name = target.name
        self.type = target.type
        self.status = target.status
        self.properties = target.properties
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
        self._migrate_schema()
        self.Session = SessionLocal
        self.current_target: Optional[Target] = None
        # Restore last selected target from database
        self._restore_current_target()

    def _migrate_schema(self):
        """Add any missing columns to existing tables (lightweight migration)."""
        import sqlite3
        from sqlalchemy import inspect as sa_inspect

        inspector = sa_inspect(engine)
        if "targets" not in inspector.get_table_names():
            return

        existing_cols = {col["name"] for col in inspector.get_columns("targets")}
        migrations = {
            "created_at": "DATETIME",
            "updated_at": "DATETIME",
        }

        with engine.connect() as conn:
            for col_name, col_type in migrations.items():
                if col_name not in existing_cols:
                    conn.execute(
                        sqlalchemy_text(f"ALTER TABLE targets ADD COLUMN {col_name} {col_type}")
                    )
                    xlog.info(f"Migrated: added column '{col_name}' to targets table", name="target_model")
            conn.commit()

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
                existing_target.type = target.type
                existing_target.status = target.status
                existing_target.properties = target.properties
                existing_target.ip_address = target.ip_address
                existing_target.location = target.location
                existing_target.components = [comp.model_dump() for comp in target.components]
                existing_target.interfaces = [intf.model_dump() for intf in target.interfaces]
                session.commit()
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
            # Exclude the special settings pseudo-target
            targets = session.query(TargetDBModel).filter(TargetDBModel.target_id != "__settings__").all()
            result = []
            for t in targets:
                # All targets now have full fields (ip_address, location, components, interfaces)
                target_info: Dict[str, Any] = {
                    "target_id": t.target_id,
                    "name": t.name,
                    "type": t.type,
                    "status": t.status,
                    "properties": t.properties,
                    "ip_address": t.ip_address,
                    "location": t.location,
                    "components": t.components or [],
                    "interfaces": t.interfaces or [],
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "updated_at": t.updated_at.isoformat() if t.updated_at else None,
                }
                result.append(target_info)
            return result
        finally:
            session.close()

    # ---------------- current target (in-memory) ----------------

    def get_current_target(self) -> Optional[Target]:
        return self.current_target

    def set_current_target(self, target: Target) -> None:
        self.current_target = target
        # Persist the selection to database
        self._persist_current_target(target.target_id if target else None)

    def _persist_current_target(self, target_id: Optional[str]) -> None:
        """Store the current target selection in the database using raw SQL."""
        try:
            settings_id = "__settings__"
            props = json.dumps({'current_target_id': target_id})
            with engine.connect() as conn:
                row = conn.execute(
                    sqlalchemy_text("SELECT target_id FROM targets WHERE target_id = :sid"),
                    {"sid": settings_id},
                ).fetchone()
                if row:
                    conn.execute(
                        sqlalchemy_text("UPDATE targets SET properties = :props WHERE target_id = :sid"),
                        {"props": props, "sid": settings_id},
                    )
                else:
                    conn.execute(
                        sqlalchemy_text(
                            "INSERT INTO targets (target_id, name, type, status, properties) "
                            "VALUES (:sid, :name, :type, :status, :props)"
                        ),
                        {"sid": settings_id, "name": "System Settings", "type": "settings", "status": "system", "props": props},
                    )
                conn.commit()
        except Exception as e:
            xlog.error(f"Failed to persist current target: {e}", name="target_model")

    def _restore_current_target(self) -> None:
        """Restore the last selected target from database using raw SQL."""
        try:
            settings_id = "__settings__"
            with engine.connect() as conn:
                row = conn.execute(
                    sqlalchemy_text("SELECT properties FROM targets WHERE target_id = :sid"),
                    {"sid": settings_id},
                ).fetchone()
                if row and row[0]:
                    props = json.loads(row[0]) if isinstance(row[0], str) else row[0]
                    target_id = props.get('current_target_id')
                    if target_id:
                        targets = self.get_all_targets()
                        target_dict = next((t for t in targets if t['target_id'] == target_id), None)
                        if target_dict:
                            self.current_target = self.create_target_instance(target_dict)
                            xlog.info(f"Restored current target: {self.current_target.name}", name="target_model")
        except Exception as e:
            xlog.warning(f"Failed to restore current target: {e}", name="target_model")

    # ---------------- hydrate / update helpers ----------------

    def create_target_instance(self, target_data: Dict[str, Any]) -> Target:
        """
        Create a domain Target instance from a dict (as returned by get_all_targets or request payloads).
        All target types now share the same fields (ip_address, location, components, interfaces).
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
            "ip_address": target_data.get("ip_address"),
            "location": target_data.get("location"),
            "components": components,
            "interfaces": interfaces,
        }

        # Use Vehicle class for vehicle type (has ADB helper methods)
        # Use GenericTarget for all other types
        if target_type == "vehicle":
            return Vehicle(**common_kwargs)

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

    def add_target(self, target_data: Dict[str, Any]) -> bool:
        """
        Add a new target from dict payload. Returns success flag.
        """
        try:
            target_instance = self.create_target_instance(target_data)
            self.save_target(target_instance)
            return True
        except Exception as e:
            xlog.error(f"add_target failed: {e}", name="target_model")
            return False

    def delete_target(self, target_id: str) -> bool:
        """
        Delete a target by target_id. Returns success flag.
        """
        session = self.Session()
        try:
            target = session.query(TargetDBModel).filter_by(target_id=target_id).first()
            if not target:
                xlog.warning(f"Target with id '{target_id}' not found", name="target_model")
                return False
            
            session.delete(target)
            session.commit()
            
            # Clear current_target if it matches the deleted target
            if self.current_target and getattr(self.current_target, "target_id", None) == target_id:
                self.current_target = None
            
            xlog.info(f"Successfully deleted target '{target_id}'", name="target_model")
            return True
        except Exception as e:
            session.rollback()
            xlog.error(f"delete_target failed: {e}", name="target_model")
            return False
        finally:
            session.close()

    def export_targets_to_json(self, json_file_path: str, backup_original: bool = False) -> bool:
        """
        Export all targets to a JSON file. Returns success flag.
        """
        try:
            # Get all targets
            targets = self.get_all_targets()
            
            # Backup original file if requested and it exists
            if backup_original and os.path.exists(json_file_path):
                import shutil
                from datetime import datetime
                backup_path = f"{json_file_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                shutil.copy2(json_file_path, backup_path)
                xlog.info(f"Backed up original file to: {backup_path}", name="target_model")
            
            # Write targets to JSON file
            data = {"targets": targets}
            with open(json_file_path, "w") as file:
                json.dump(data, file, indent=2)
            
            xlog.info(f"Successfully exported {len(targets)} targets to: {json_file_path}", name="target_model")
            return True
        except Exception as e:
            xlog.error(f"export_targets_to_json failed: {e}", name="target_model")
            return False

    def parse_and_set_target_from_json(self, json_file_path: str, force_overwrite: bool = False) -> None:
        xlog.debug(f"Reading JSON file from: {json_file_path}", name="target_model")
        if not os.path.exists(json_file_path):
            xlog.error(f"File not found: {json_file_path}", name="target_model")
            return

        with open(json_file_path, "r") as file:
            data = json.load(file)

        existing_ids: set[str] = set()
        if not force_overwrite:
            session = self.Session()
            try:
                existing_ids = {row[0] for row in session.query(TargetDBModel.target_id).all()}
            finally:
                session.close()

        imported_count = 0
        skipped_count = 0
        for target in data.get("targets", []):
            target_id = target.get("target_id", "")
            if not target_id:
                xlog.warning("Skipping target import: missing target_id", name="target_model")
                skipped_count += 1
                continue

            if (not force_overwrite) and (target_id in existing_ids):
                skipped_count += 1
                continue

            target_type = target.get("type", "vehicle")
            target_class = self.targets.get(target_type, Vehicle)

            # Re-hydrate components/interfaces using the domain factory
            components = [ComponentFactory.create_component(c) for c in target.get("components", [])]
            interfaces = target.get("interfaces", [])

            target_instance = target_class(
                target_id=target_id,
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

        xlog.info(
            f"Imported {imported_count} targets (skipped {skipped_count}) from JSON file: {json_file_path}",
            name="target_model",
        )


