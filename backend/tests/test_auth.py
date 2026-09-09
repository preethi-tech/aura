"""Authentication tests, including strict cross-system export identity."""
import pytest
from fastapi import HTTPException

from app.auth import get_authenticated_user, get_current_user
from app.config import settings


def test_local_app_keeps_default_user():
    assert get_current_user(None) == settings.DEFAULT_USER


def test_sensitive_export_rejects_local_identity():
    with pytest.raises(HTTPException) as exc:
        get_authenticated_user(None)
    assert exc.value.status_code == 403


def test_cloud_storage_requires_sign_in(monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "firestore")
    with pytest.raises(HTTPException) as exc:
        get_current_user(None)
    assert exc.value.status_code == 401


def test_strict_auth_returns_verified_firebase_uid(monkeypatch):
    from firebase_admin import auth

    monkeypatch.setattr(settings, "STORAGE_BACKEND", "firestore")
    monkeypatch.setattr(auth, "verify_id_token", lambda token: {"uid": "uid-123"})
    assert get_authenticated_user("Bearer valid-token") == "uid-123"
