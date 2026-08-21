"""
conftest.py — pytest fixtures shared across all Module 3 tests.

Uses an in-memory SQLite DB for isolation.
"""

import os
import sys

# Make sure the backend/ directory is on sys.path so imports resolve
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from flask_socketio import SocketIO

# Point to in-memory DB BEFORE importing anything that touches the DB
os.environ["DATABASE_URL"] = "sqlite://"  # in-memory SQLite
os.environ["MODULE3_START_BACKGROUND"] = "0"
os.environ["MODULE1_START_BACKGROUND"] = "0"

from database import Base, SessionLocal, engine, init_db
from app import create_app


@pytest.fixture(scope="session")
def flask_app():
    """Create application configured for testing."""
    _app = create_app({"TESTING": True, "ML_ENABLE_ASYNC_PREDICTIONS": False})
    return _app


@pytest.fixture(scope="session")
def test_client(flask_app):
    return flask_app.test_client()


@pytest.fixture(scope="session")
def socketio_test_client(flask_app):
    from flask_socketio import SocketIO
    # Access the module-level socketio instance
    import app as app_module
    return app_module.socketio.test_client(flask_app, namespace="/fault-events")


@pytest.fixture(autouse=True)
def clean_db():
    """Wipe fault_events table between tests for isolation."""
    from models.fault_events import FaultEvent
    db = SessionLocal()
    try:
        db.query(FaultEvent).delete()
        db.commit()
    finally:
        db.close()
