from __future__ import annotations

import datetime

from sat_toolkit.adapters.django.device_models import DeviceDriverState
from sat_toolkit.adapters.django.sqlalchemy_database import get_default_sqlalchemy_db


class DjangoDriverStateRepository:
    """SQLAlchemy-backed driver state repo (adapter layer).

    NOTE: This uses the SQLAlchemy DB factory that is configured via Django settings.
    """

    def __init__(self) -> None:
        self._db = get_default_sqlalchemy_db()

    def get_enabled(self, driver_name: str) -> bool | None:
        session = self._db.SessionLocal()
        try:
            row = session.query(DeviceDriverState).filter_by(driver_name=driver_name).first()
            return None if row is None else bool(row.enabled)
        except Exception:
            return None
        finally:
            session.close()

    def set_enabled(self, driver_name: str, enabled: bool, description: str | None = None) -> None:
        session = self._db.SessionLocal()
        try:
            row = session.query(DeviceDriverState).filter_by(driver_name=driver_name).first()
            if row:
                row.enabled = bool(enabled)
                row.last_updated = datetime.datetime.now()
                if description is not None:
                    row.description = description
            else:
                row = DeviceDriverState(driver_name=driver_name, enabled=bool(enabled), description=description)
                session.add(row)
            session.commit()
        except Exception:
            session.rollback()
        finally:
            session.close()

    def list_enabled(self) -> dict[str, bool]:
        session = self._db.SessionLocal()
        try:
            rows = session.query(DeviceDriverState).all()
            return {r.driver_name: bool(r.enabled) for r in rows}
        except Exception:
            return {}
        finally:
            session.close()


