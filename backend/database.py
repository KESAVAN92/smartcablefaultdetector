"""
SQLAlchemy database setup — shared by all modules.
Module 3 only creates the fault_events table here.
M1/M2 will add their own models when they push their branches.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite:///./cable_fault.db",
)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def init_db():
    """
    Create only the tables Module 3 owns.
    M1 / M2 call their own init_db() when they push their branches.
    """
    from models.fault_events import FaultEvent  # noqa: F401  — only M3's table
    Base.metadata.create_all(bind=engine)
