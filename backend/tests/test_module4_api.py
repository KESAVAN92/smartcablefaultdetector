import os
import tempfile
import sqlite3
import json

import pytest

from app import create_app


def test_register_login_and_reports_flow(tmp_path):
    db_path = str(tmp_path / "test-module4.sqlite3")
    app = create_app({
        "TESTING": True,
        "DATABASE_PATH": db_path,
        "MODULE1_START_BACKGROUND": False,
        "JWT_SECRET": "test-jwt-secret",
    })
    client = app.test_client()

    # Register first admin
    r = client.post("/api/module4/auth/register", json={"email": "admin@t.local", "password": "pw", "role": "admin"})
    assert r.status_code == 201

    # Login
    r = client.post("/api/module4/auth/login", json={"email": "admin@t.local", "password": "pw"})
    assert r.status_code == 200
    token = r.get_json()["access_token"]

    # Without data, reports should return empty list
    r = client.get("/api/module4/reports/fault-history", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert isinstance(r.get_json().get("items"), list)
