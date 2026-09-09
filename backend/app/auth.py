"""Firebase Authentication middleware.

Verifies Firebase ID tokens from the frontend. When Firebase Auth is not
configured (no FIREBASE_PROJECT_ID), falls back to the default local user.
"""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException

from .config import settings


def _verify_authorization(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Firebase sign-in is required")
    token = authorization.split("Bearer ", 1)[1]
    try:
        from firebase_admin import auth
        decoded = auth.verify_id_token(token)
        return decoded["uid"]
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def get_current_user(authorization: str | None = Header(default=None)) -> str:
    """Extract user ID from Firebase ID token, or fall back to default user."""
    if not settings.firestore_enabled:
        return settings.DEFAULT_USER
    return _verify_authorization(authorization)


def get_authenticated_user(
    authorization: str | None = Header(default=None),
) -> str:
    """Require a verified cloud identity for sensitive cross-system exports."""
    if not settings.firestore_enabled:
        raise HTTPException(
            status_code=403,
            detail="BigQuery export requires Firebase-backed cloud storage and sign-in",
        )
    return _verify_authorization(authorization)
