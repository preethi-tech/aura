# Deploying Aura

Aura is a single container (FastAPI + static frontend). It runs anywhere that
runs a container. Below: local Docker, then Google Cloud Run.

## 1. Build & run locally with Docker

```bash
# from the aura/ project root
docker build -t aura:local .
docker run --rm -p 8080:8080 aura:local
# open http://localhost:8080
```

Enable Gemini by passing the key as an env var:

```bash
docker run --rm -p 8080:8080 -e GEMINI_API_KEY=YOUR_KEY aura:local
```

## 2. Deploy to Google Cloud Run

**Prerequisites:** a GCP project, billing enabled, and the `gcloud` CLI
installed and authenticated (`gcloud auth login`).

```bash
# 0) Set your project and region
gcloud config set project YOUR_PROJECT_ID
gcloud config set run/region us-central1

# 1) Enable the required services (one-time)
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com

# 2) Deploy straight from source (Cloud Build builds the Dockerfile for you)
gcloud run deploy aura \
  --source . \
  --allow-unauthenticated \
  --port 8080

# 3) (optional) enable Gemini by setting the API key as an env var
gcloud run services update aura \
  --update-env-vars GEMINI_API_KEY=YOUR_KEY,GEMINI_MODEL=gemini-2.5-flash
```

`gcloud run deploy` prints the public HTTPS URL when it finishes.

### Recommended hardening
- Store the key in **Secret Manager** instead of a plain env var:
  ```bash
  echo -n "YOUR_KEY" | gcloud secrets create aura-gemini-key --data-file=-
  gcloud run services update aura \
    --update-secrets GEMINI_API_KEY=aura-gemini-key:latest
  ```
- Drop `--allow-unauthenticated` and put **Identity-Aware Proxy** (IAP) or
  Firebase-free OAuth in front if this holds real data.

## 3. Important: storage on Cloud Run is ephemeral

Aura's default SQLite file lives in the container's writable layer, which is
**per-instance and lost on restart / scale events**. That's fine for a demo or a
single always-on instance, but for real persistence:

- Set `--max-instances 1` and `--min-instances 1` for a simple single-instance
  demo, **or**
- Mount a **Cloud Storage** bucket via the Cloud Run GCS volume mount and point
  `AURA_DB_PATH` at it, **or**
- Swap SQLite for **Cloud SQL** (Postgres) — the `db.py` layer is small and
  isolated, so this is a contained change.
