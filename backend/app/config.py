"""Application configuration.

All settings are read from environment variables (optionally via a .env file).
Nothing here is required for the app to run: with no GEMINI_API_KEY the app
falls back to a fully deterministic, offline linguistic analyzer. With no
FIREBASE_PROJECT_ID, the app uses local SQLite.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the backend directory if present.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(_BACKEND_DIR / ".env")

# Repo root (aura/) so we can serve the sibling frontend folder.
PROJECT_ROOT = _BACKEND_DIR.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"


class Settings:
    # --- Gemini (optional) --------------------------------------------------
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()

    # --- Firebase (optional) ------------------------------------------------
    FIREBASE_PROJECT_ID: str = os.getenv("FIREBASE_PROJECT_ID", "").strip()
    FIREBASE_CREDENTIALS: str = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    FIREBASE_WEB_API_KEY: str = os.getenv("FIREBASE_WEB_API_KEY", "").strip()

    # --- Storage ------------------------------------------------------------
    # "firestore" or "sqlite". Auto-selects firestore if FIREBASE_PROJECT_ID is set.
    STORAGE_BACKEND: str = os.getenv("STORAGE_BACKEND", "").strip()
    DB_PATH: str = os.getenv("AURA_DB_PATH", str(_BACKEND_DIR / "aura.db"))

    # --- App ----------------------------------------------------------------
    DEFAULT_USER: str = os.getenv("AURA_USER", "local")
    HOST: str = os.getenv("AURA_HOST", "127.0.0.1")
    PORT: int = int(os.getenv("AURA_PORT", "8000"))

    # --- Cloud Logging (optional) -------------------------------------------
    CLOUD_LOGGING_ENABLED: bool = os.getenv("CLOUD_LOGGING_ENABLED", "").strip().lower() in ("true", "1", "yes")

    @property
    def gemini_enabled(self) -> bool:
        return bool(self.GEMINI_API_KEY)

    @property
    def firestore_enabled(self) -> bool:
        if self.STORAGE_BACKEND == "firestore":
            return True
        if self.STORAGE_BACKEND == "sqlite":
            return False
        return bool(self.FIREBASE_PROJECT_ID)


settings = Settings()
