"""Pytest fixtures. Isolates tests onto a temp DB and forces offline mode.

Environment must be set BEFORE app modules import settings, so we do it at the
top of this file (pytest imports conftest first).
"""
import os
import pathlib
import tempfile

# Point the app at a throwaway DB and force the offline (no-Gemini) path.
_TEST_DB = os.path.join(tempfile.gettempdir(), "aura_test.db")
os.environ["AURA_DB_PATH"] = _TEST_DB
os.environ["GEMINI_API_KEY"] = ""
pathlib.Path(_TEST_DB).unlink(missing_ok=True)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_db():
    from app.config import settings
    from app.db import delete_all, init_db
    init_db()
    delete_all(settings.DEFAULT_USER)
    yield


@pytest.fixture()
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c
