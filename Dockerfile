# Aura — single-container image (API + static frontend)
FROM python:3.12-slim

WORKDIR /app

# Install deps first for better layer caching.
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# App code + static frontend (kept as siblings; config.py serves ../frontend).
COPY backend ./backend
COPY frontend ./frontend

ENV AURA_HOST=0.0.0.0
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT:-8080}/api/health')" || exit 1

# Cloud Run provides $PORT (defaults to 8080). Shell form expands it; `exec`
# keeps uvicorn as PID 1 for clean signal handling.
CMD exec uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8080}
