"""Opt-in, pseudonymous BigQuery analytics for Aura."""
from __future__ import annotations

import hashlib
import hmac
import math
import re
from datetime import datetime, timezone

from .config import settings

METRIC_VERSION = "aura-index-v1"
SCHEMA_VERSION = 1
MIN_COHORT_SIZE = 10
MAX_EXPORT_DAYS = 366
RETENTION_DAYS = 400
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,1023}$")

PRIVACY_CONTRACT = {
    "consent": "Each export requires a fresh explicit confirmation.",
    "included": [
        "HMAC participant pseudonym", "metric date", "Aura Index",
        "metric version", "synthetic/user provenance", "export timestamp",
    ],
    "excluded": [
        "journal text", "name", "email", "Firebase UID", "auth token",
        "trusted-contact data", "assessment data", "crisis text or flag",
        "tier", "linguistic features", "raw sleep, social or activity values",
    ],
    "cohort_rule": (
        f"Cross-user metrics are hidden below {MIN_COHORT_SIZE} real opted-in participants."
    ),
    "retention": f"Daily partitions expire after {RETENTION_DAYS} days.",
}

_EXPECTED_SCHEMA = [
    ("record_id", "STRING", "REQUIRED"),
    ("participant_id", "STRING", "REQUIRED"),
    ("metric_date", "DATE", "REQUIRED"),
    ("aura_index", "FLOAT", "REQUIRED"),
    ("metric_version", "STRING", "REQUIRED"),
    ("data_source", "STRING", "REQUIRED"),
    ("exported_at", "TIMESTAMP", "REQUIRED"),
    ("schema_version", "INTEGER", "REQUIRED"),
]


class BigQueryAnalyticsError(RuntimeError):
    pass


def _missing_settings() -> list[str]:
    required = {
        "BIGQUERY_PROJECT_ID": settings.BIGQUERY_PROJECT_ID,
        "BIGQUERY_PSEUDONYM_SALT": settings.BIGQUERY_PSEUDONYM_SALT,
        "FIREBASE_PROJECT_ID": settings.FIREBASE_PROJECT_ID,
    }
    return [name for name, value in required.items() if not value]


def _validate_identifiers() -> None:
    for name, value in (
        ("BIGQUERY_DATASET", settings.BIGQUERY_DATASET),
        ("BIGQUERY_TABLE", settings.BIGQUERY_TABLE),
    ):
        if not _IDENTIFIER.fullmatch(value):
            raise BigQueryAnalyticsError(f"{name} is not a valid BigQuery identifier")


def table_id() -> str:
    _validate_identifiers()
    return (
        f"{settings.BIGQUERY_PROJECT_ID}."
        f"{settings.BIGQUERY_DATASET}.{settings.BIGQUERY_TABLE}"
    )


def status() -> dict:
    missing = _missing_settings()
    enabled = settings.bigquery_enabled and not missing
    result = {
        "enabled": enabled,
        "requested": settings.BIGQUERY_ENABLED,
        "configured": not missing,
        "dataset": settings.BIGQUERY_DATASET,
        "table": settings.BIGQUERY_TABLE,
        "location": settings.BIGQUERY_LOCATION,
        "metric_version": METRIC_VERSION,
        "privacy": PRIVACY_CONTRACT,
    }
    if missing:
        result["missing"] = missing
    if enabled:
        result["table_id"] = table_id()
    return result


def pseudonymize(user_id: str) -> str:
    if not settings.BIGQUERY_PSEUDONYM_SALT:
        raise BigQueryAnalyticsError("BIGQUERY_PSEUDONYM_SALT is required")
    canonical = "\0".join((
        "aura-bq-pseudonym-v1", "firebase",
        settings.FIREBASE_PROJECT_ID, user_id,
    ))
    digest = hmac.new(
        settings.BIGQUERY_PSEUDONYM_SALT.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"p1_{digest}"


def _record_id(participant_id: str, metric_date: str, aura_index: float,
               exported_at: str) -> str:
    canonical = "\0".join((
        participant_id, metric_date, METRIC_VERSION,
        f"{aura_index:.1f}", exported_at,
    ))
    return hmac.new(
        settings.BIGQUERY_PSEUDONYM_SALT.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def build_rows(
    user_id: str,
    entries: list[dict],
    timeline: list[dict],
    *,
    exported_at: str | None = None,
) -> list[dict]:
    participant_id = pseudonymize(user_id)
    entry_by_date = {entry["date"]: entry for entry in entries}
    exported_at = exported_at or datetime.now(timezone.utc).isoformat()
    rows: list[dict] = []
    for day in timeline:
        if day.get("calibrating") or day.get("aura_index") is None:
            continue
        index = float(day["aura_index"])
        if not math.isfinite(index) or not 0.0 <= index <= 100.0:
            continue
        metric_date = day.get("date")
        if not metric_date:
            continue
        source = entry_by_date.get(metric_date, {}).get("source", "user")
        if source not in ("user", "synthetic_demo"):
            source = "user"
        rows.append({
            "record_id": _record_id(
                participant_id, metric_date, index, exported_at),
            "participant_id": participant_id,
            "metric_date": metric_date,
            "aura_index": round(index, 1),
            "metric_version": METRIC_VERSION,
            "data_source": source,
            "exported_at": exported_at,
            "schema_version": SCHEMA_VERSION,
        })
    return rows[-MAX_EXPORT_DAYS:]


def _bigquery_module():
    try:
        from google.cloud import bigquery
        return bigquery
    except ImportError as exc:
        raise BigQueryAnalyticsError(
            "google-cloud-bigquery is not installed"
        ) from exc


def _client():
    bigquery = _bigquery_module()
    return bigquery.Client(project=settings.BIGQUERY_PROJECT_ID)


def _schema(bigquery):
    return [bigquery.SchemaField(name, kind, mode=mode)
            for name, kind, mode in _EXPECTED_SCHEMA]


def _ensure_table(client) -> None:
    bigquery = _bigquery_module()
    dataset_id = f"{settings.BIGQUERY_PROJECT_ID}.{settings.BIGQUERY_DATASET}"
    try:
        client.get_dataset(dataset_id)
    except Exception as exc:
        raise BigQueryAnalyticsError(
            f"BigQuery dataset {dataset_id} is unavailable; create it and grant the Cloud Run identity access"
        ) from exc
    table = bigquery.Table(table_id(), schema=_schema(bigquery))
    table.description = (
        "Opt-in pseudonymous Aura Index snapshots; no raw journal, identity, crisis, contact or sensor data."
    )
    table.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY,
        field="metric_date",
        expiration_ms=RETENTION_DAYS * 86_400_000,
    )
    table.require_partition_filter = True
    table.clustering_fields = ["participant_id", "metric_version"]
    client.create_table(table, exists_ok=True)
    existing = client.get_table(table_id())
    actual = [(f.name, f.field_type, f.mode) for f in existing.schema]
    if actual != _EXPECTED_SCHEMA:
        raise BigQueryAnalyticsError(
            "Existing BigQuery table schema does not match Aura analytics v1"
        )
    partition = getattr(existing, "time_partitioning", None)
    if not partition or partition.field != "metric_date":
        raise BigQueryAnalyticsError(
            "Existing BigQuery table is not partitioned by metric_date"
        )


def _require_enabled() -> None:
    if not settings.bigquery_enabled or _missing_settings():
        missing = ", ".join(_missing_settings()) or "BIGQUERY_ENABLED=true"
        raise BigQueryAnalyticsError(
            f"BigQuery analytics is disabled or incomplete: {missing}"
        )


def sync(user_id: str, entries: list[dict], timeline: list[dict]) -> dict:
    _require_enabled()
    rows = build_rows(user_id, entries, timeline)
    if not rows:
        return {
            "enabled": True, "synced": 0, "table_id": table_id(),
            "metric_version": METRIC_VERSION, "privacy": PRIVACY_CONTRACT,
        }
    client = _client()
    _ensure_table(client)
    errors: list = []
    try:
        for start in range(0, len(rows), 500):
            batch = rows[start:start + 500]
            errors.extend(client.insert_rows_json(
                table_id(),
                batch,
                row_ids=[row["record_id"] for row in batch],
                skip_invalid_rows=False,
                ignore_unknown_values=False,
            ))
    except Exception as exc:
        raise BigQueryAnalyticsError(
            "BigQuery export failed; retry with the same signed-in account"
        ) from exc
    if errors:
        raise BigQueryAnalyticsError(
            f"BigQuery rejected {len(errors)} row batch(es)"
        )
    sources = {row["data_source"] for row in rows}
    return {
        "enabled": True,
        "synced": len(rows),
        "table_id": table_id(),
        "metric_version": METRIC_VERSION,
        "data_mode": "demo" if sources == {"synthetic_demo"} else "user",
        "privacy": PRIVACY_CONTRACT,
    }


def _to_json(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _query_config(bigquery, participant_id: str):
    return bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter(
                "participant_id", "STRING", participant_id),
            bigquery.ScalarQueryParameter(
                "metric_version", "STRING", METRIC_VERSION),
        ],
        labels={"app": "aura", "feature": "privacy_analytics"},
        maximum_bytes_billed=settings.BIGQUERY_MAX_BYTES_BILLED,
    )


def summary(user_id: str) -> dict:
    if not settings.bigquery_enabled:
        return {**status(), "available": False}
    _require_enabled()
    client = _client()
    _ensure_table(client)
    participant_id = pseudonymize(user_id)
    sql = f"""
    WITH ranked AS (
      SELECT *, ROW_NUMBER() OVER (
        PARTITION BY participant_id, metric_date, metric_version
        ORDER BY exported_at DESC, record_id DESC
      ) AS row_rank
      FROM `{table_id()}`
      WHERE metric_date >= DATE_SUB(CURRENT_DATE(), INTERVAL {MAX_EXPORT_DAYS} DAY)
        AND metric_version = @metric_version
        AND aura_index BETWEEN 0 AND 100
    ),
    dedup AS (
      SELECT * EXCEPT(row_rank) FROM ranked WHERE row_rank = 1
    ),
    real_cohort AS (
      SELECT * FROM dedup WHERE data_source = 'user'
    ),
    cohort AS (
      SELECT
        COUNT(DISTINCT participant_id) AS participants,
        COUNT(*) AS daily_records,
        ROUND(AVG(aura_index), 1) AS avg_aura_index,
        ROUND(100 * SAFE_DIVIDE(COUNTIF(aura_index >= 50), COUNT(*)), 1)
          AS elevated_day_pct
      FROM real_cohort
    ),
    mine AS (
      SELECT
        COUNT(*) AS my_daily_records,
        COUNTIF(data_source = 'synthetic_demo') AS my_demo_records,
        ROUND(AVG(aura_index), 1) AS my_avg_aura_index,
        ROUND(100 * SAFE_DIVIDE(COUNTIF(aura_index >= 50), COUNT(*)), 1)
          AS my_elevated_day_pct,
        MIN(metric_date) AS first_date,
        MAX(metric_date) AS last_date
      FROM dedup WHERE participant_id = @participant_id
    )
    SELECT cohort.*, mine.* FROM cohort CROSS JOIN mine
    """
    bigquery = _bigquery_module()
    try:
        rows = list(client.query(
            sql,
            job_config=_query_config(bigquery, participant_id),
            location=settings.BIGQUERY_LOCATION,
        ).result())
    except Exception as exc:
        raise BigQueryAnalyticsError(
            "BigQuery summary query failed; verify dataset location and IAM"
        ) from exc
    if not rows:
        return {"enabled": True, "available": False, "table_id": table_id()}
    raw = {key: _to_json(value)
           for key, value in dict(rows[0].items()).items()}
    participants = int(raw.get("participants") or 0)
    my_records = int(raw.get("my_daily_records") or 0)
    demo_records = int(raw.get("my_demo_records") or 0)
    personal = {
        "daily_records": my_records,
        "demo_records": demo_records,
        "data_mode": "demo" if my_records and demo_records == my_records else "user",
        "avg_aura_index": raw.get("my_avg_aura_index"),
        "elevated_day_pct": raw.get("my_elevated_day_pct"),
        "first_date": raw.get("first_date"),
        "last_date": raw.get("last_date"),
    }
    cohort = {
        "available": participants >= MIN_COHORT_SIZE,
        "participants": participants,
    }
    if cohort["available"]:
        cohort.update({
            "daily_records": int(raw.get("daily_records") or 0),
            "avg_aura_index": raw.get("avg_aura_index"),
            "elevated_day_pct": raw.get("elevated_day_pct"),
            "label": "Opted-in users with eligible real check-ins",
        })
    else:
        cohort["reason"] = (
            f"Cohort metrics unlock at {MIN_COHORT_SIZE} real opted-in participants; synthetic demo rows never count."
        )
    return {
        "enabled": True,
        "available": my_records > 0,
        "table_id": table_id(),
        "metric_version": METRIC_VERSION,
        "personal": personal,
        "cohort": cohort,
        "privacy": PRIVACY_CONTRACT,
    }


def delete_user(user_id: str) -> dict:
    _require_enabled()
    client = _client()
    _ensure_table(client)
    participant_id = pseudonymize(user_id)
    bigquery = _bigquery_module()
    sql = f"""
    DELETE FROM `{table_id()}`
    WHERE metric_date >= DATE_SUB(CURRENT_DATE(), INTERVAL {RETENTION_DAYS} DAY)
      AND participant_id = @participant_id
      AND metric_version = @metric_version
    """
    try:
        job = client.query(
            sql,
            job_config=_query_config(bigquery, participant_id),
            location=settings.BIGQUERY_LOCATION,
        )
        job.result()
    except Exception as exc:
        raise BigQueryAnalyticsError(
            "BigQuery deletion is temporarily unavailable; recent streaming rows may need up to 30 minutes before deletion"
        ) from exc
    return {
        "deleted": int(job.num_dml_affected_rows or 0),
        "table_id": table_id(),
        "note": (
            "BigQuery time-travel and fail-safe retention can preserve deleted data temporarily."
        ),
    }
