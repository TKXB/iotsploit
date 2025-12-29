"""
Pure SQLAlchemy database primitives (no Django dependency).

This module is an infrastructure adapter that can be reused outside Django.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker


@dataclass(frozen=True)
class SqlAlchemyDb:
    engine: object
    SessionLocal: object
    Base: object


def create_sqlalchemy_db(db_url: str, *, echo: bool = False) -> SqlAlchemyDb:
    engine = create_engine(db_url, echo=echo)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base = declarative_base()
    return SqlAlchemyDb(engine=engine, SessionLocal=SessionLocal, Base=Base)


