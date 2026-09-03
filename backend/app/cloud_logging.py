"""Google Cloud Logging integration.

When CLOUD_LOGGING_ENABLED=true AND running on GCP (or with credentials),
routes Python logs through Cloud Logging. Locally, standard console logging
is used.
"""
from __future__ import annotations

import logging

from .config import settings

logger = logging.getLogger("aura")


def setup_logging() -> None:
    """Configure logging: Cloud Logging on GCP, console locally."""
    if settings.CLOUD_LOGGING_ENABLED:
        try:
            import google.cloud.logging
            client = google.cloud.logging.Client()
            client.setup_logging()
            logger.info("Cloud Logging enabled")
            return
        except Exception as e:
            logging.warning(f"Cloud Logging init failed, using console: {e}")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info("Console logging enabled")
