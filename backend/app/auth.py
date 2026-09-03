"""Firebase Authentication middleware.

Verifies Firebase ID tokens from the frontend. When Firebase Auth is not
configured (no FIREBASE_PROJECT_ID), falls back to the default local user.
"""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException

from .config import settings


def get_current_user(authorization: str | None = Header(default=None)) -> str:
    """Extract user ID from Firebase ID token, or fall back to default user."""
    if not settings.firestore_enabled or not authorization:
        return settings.DEFAULT_USER

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    token = authorization.split("Bearer ", 1)[1]
    try:
        from firebase_admin import auth
        decoded = auth.verify_id_token(token)
        return decoded["uid"]
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
