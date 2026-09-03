"""Application configuration.

All settings are read from environment variables (optionally via a .env file).
Nothing here is required for the app to run: with no GEMINI_API_KEY the app
falls back to a fully deterministic, offline linguistic analyzer.
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

    # --- Storage ------------------------------------------------------------
    # Local SQLite file. No external database / no Firebase.
    DB_PATH: str = os.getenv(
        "AURA_DB_PATH", str(_BACKEND_DIR / "aura.db")
    )

    # --- App ----------------------------------------------------------------
    # Single local user by default; the schema supports multiple users.
    DEFAULT_USER: str = os.getenv("AURA_USER", "local")
    HOST: str = os.getenv("AURA_HOST", "127.0.0.1")
    PORT: int = int(os.getenv("AURA_PORT", "8000"))

    @property
    def gemini_enabled(self) -> bool:
        return bool(self.GEMINI_API_KEY)


settings = Settings()
