from __future__ import annotations

from pathlib import Path
import sys

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import create_app


@pytest.fixture()
def app(tmp_path: Path):
    app = create_app(
        {
            "TESTING": True,
            "DATABASE_PATH": str(tmp_path / "test-module2.sqlite3"),
            "MODULE2_LAYOUT_DIR": str(tmp_path / "layout"),
        }
    )
    return app


@pytest.fixture()
def client(app):
    return app.test_client()
