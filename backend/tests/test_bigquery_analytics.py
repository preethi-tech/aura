"""Tests for the opt-in, pseudonymous BigQuery analytics feature."""
from __future__ import annotations

import json
from datetime import date

import pytest

from app import bigquery_analytics as analytics
from app.config import settings


def _enable(monkeypatch):
    monkeypatch.setattr(settings, "BIGQUERY_ENABLED", True)
    monkeypatch.setattr(settings, "BIGQUERY_PROJECT_ID", "demo-project")
    monkeypatch.setattr(settings, "BIGQUERY_DATASET", "aura_analytics")
    monkeypatch.setattr(settings, "BIGQUERY_TABLE", "daily_signals")
    monkeypatch.setattr(settings, "BIGQUERY_LOCATION", "US")
    monkeypatch.setattr(settings, "BIGQUERY_PSEUDONYM_SALT", "test-only-salt")
    monkeypatch.setattr(settings, "BIGQUERY_MAX_BYTES_BILLED", 100_000_000)
    monkeypatch.setattr(settings, "FIREBASE_PROJECT_ID", "firebase-project")


def _data():
    entries = [{
        "date": "2026-01-01",
        "journal_text": "PRIVATE JOURNAL CONTENT",
        "sleep_hours": 6.5,
        "social_count": 2,
        "energy": 3,
        "steps": 4200,
        "active_minutes": 20,
        "screen_time_min": 300,
        "features": {"negative_sentiment": 0.7},
        "safety_flag": True,
        "source": "synthetic_demo",
    }]
    timeline = [{
        "date": "2026-01-01",
        "aura_index": 62.0,
        "tier": 3,
        "calibrating": False,
        "safety_flag": True,
        "neg_sentiment": 0.7,
        "contributions": {"sleep_hours": 1.2, "energy": 0.4},
    }]
    return entries, timeline


def _authenticated(client):
    import app.main as main

    main.app.dependency_overrides[main.get_authenticated_user] = (
        lambda: settings.DEFAULT_USER
    )
    return main


def test_status_disabled_by_default():
    result = analytics.status()
    assert result["enabled"] is False
    assert result["privacy"]["excluded"]


def test_pseudonym_is_stable_namespaced_and_secret_keyed(monkeypatch):
    _enable(monkeypatch)
    first = analytics.pseudonymize("firebase-user-123")
    second = analytics.pseudonymize("firebase-user-123")
    other = analytics.pseudonymize("firebase-user-456")
    assert first == second
    assert first != other
    assert first.startswith("p1_")
    assert "firebase-user-123" not in first
    assert len(first) == 67


def test_export_allowlist_excludes_sensitive_content(monkeypatch):
    _enable(monkeypatch)
    entries, timeline = _data()
    rows = analytics.build_rows(
        "firebase-user-123", entries, timeline,
        exported_at="2026-01-02T00:00:00+00:00",
    )
    assert len(rows) == 1
    encoded = json.dumps(rows)
    for forbidden in (
        "PRIVATE JOURNAL CONTENT", "firebase-user-123", "safety_flag",
        "journal_text", "features", "sleep_hours", "tier",
        "negative_sentiment", "social_count", "steps",
    ):
        assert forbidden not in encoded
    assert set(rows[0]) == {
        "record_id", "participant_id", "metric_date", "aura_index",
        "metric_version", "data_source", "exported_at", "schema_version",
    }
    assert rows[0]["data_source"] == "synthetic_demo"
    assert rows[0]["aura_index"] == 62.0


def test_calibration_rows_are_never_exported(monkeypatch):
    _enable(monkeypatch)
    entries, timeline = _data()
    timeline[0]["calibrating"] = True
    assert analytics.build_rows("user", entries, timeline) == []


def test_invalid_dataset_identifier_is_rejected(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(settings, "BIGQUERY_DATASET", "bad-dataset; DROP TABLE")
    with pytest.raises(analytics.BigQueryAnalyticsError):
        analytics.table_id()


def test_sync_uses_strict_streaming_options_and_no_pseudonym_in_response(monkeypatch):
    _enable(monkeypatch)
    entries, timeline = _data()

    class Client:
        def __init__(self):
            self.rows = None
            self.row_ids = None
            self.options = None

        def insert_rows_json(self, table, rows, row_ids, **options):
            self.rows = rows
            self.row_ids = row_ids
            self.options = options
            return []

    client = Client()
    monkeypatch.setattr(analytics, "_client", lambda: client)
    monkeypatch.setattr(analytics, "_ensure_table", lambda unused: None)
    result = analytics.sync("firebase-user-123", entries, timeline)
    assert result["synced"] == 1
    assert client.row_ids == [client.rows[0]["record_id"]]
    assert client.options == {
        "skip_invalid_rows": False,
        "ignore_unknown_values": False,
    }
    assert "participant_id" not in result
    assert result["data_mode"] == "demo"


def test_sync_surfaces_bigquery_row_errors(monkeypatch):
    _enable(monkeypatch)
    entries, timeline = _data()

    class Client:
        def insert_rows_json(self, table, rows, row_ids, **options):
            return [{"index": 0, "errors": [{"reason": "invalid"}]}]

    monkeypatch.setattr(analytics, "_client", Client)
    monkeypatch.setattr(analytics, "_ensure_table", lambda unused: None)
    with pytest.raises(analytics.BigQueryAnalyticsError):
        analytics.sync("user", entries, timeline)


def test_summary_suppresses_small_real_cohort_and_labels_demo(monkeypatch):
    _enable(monkeypatch)

    class Row:
        def items(self):
            return {
                "participants": 0,
                "daily_records": 0,
                "avg_aura_index": None,
                "elevated_day_pct": None,
                "my_daily_records": 25,
                "my_demo_records": 25,
                "my_avg_aura_index": 41.0,
                "my_elevated_day_pct": 28.0,
                "first_date": date(2026, 1, 1),
                "last_date": date(2026, 1, 25),
            }.items()

    class Job:
        def result(self):
            return [Row()]

    class Client:
        def query(self, sql, job_config, location):
            assert "ROW_NUMBER()" in sql
            assert "data_source = 'user'" in sql
            assert "DATE_SUB" in sql
            assert location == "US"
            return Job()

    class FakeBigQuery:
        class ScalarQueryParameter:
            def __init__(self, *args):
                self.args = args

        class QueryJobConfig:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

    monkeypatch.setattr(analytics, "_client", Client)
    monkeypatch.setattr(analytics, "_ensure_table", lambda unused: None)
    monkeypatch.setattr(analytics, "_bigquery_module", lambda: FakeBigQuery)
    result = analytics.summary("user")
    assert result["available"] is True
    assert result["personal"]["daily_records"] == 25
    assert result["personal"]["data_mode"] == "demo"
    assert result["cohort"]["available"] is False
    assert result["cohort"]["participants"] == 0
    assert result["personal"]["first_date"] == "2026-01-01"


def test_table_contract_is_minimal_partitioned_schema():
    assert [field[0] for field in analytics._EXPECTED_SCHEMA] == [
        "record_id", "participant_id", "metric_date", "aura_index",
        "metric_version", "data_source", "exported_at", "schema_version",
    ]
    assert analytics.MIN_COHORT_SIZE == 10
    assert analytics.RETENTION_DAYS == 400


def test_api_rejects_local_identity_before_export(client):
    response = client.post(
        "/api/analytics/bigquery/sync", json={"consent": True}
    )
    assert response.status_code == 403


def test_api_requires_explicit_consent_after_auth(client):
    main = _authenticated(client)
    try:
        response = client.post(
            "/api/analytics/bigquery/sync", json={"consent": False}
        )
        assert response.status_code == 400
        assert "consent" in response.json()["detail"].lower()
    finally:
        main.app.dependency_overrides.pop(main.get_authenticated_user, None)


def test_api_status_and_health_advertise_bigquery(client):
    status = client.get("/api/analytics/bigquery/status")
    assert status.status_code == 200
    assert status.json()["enabled"] is False
    health = client.get("/api/health").json()
    assert health["bigquery_enabled"] is False


def test_api_sync_summary_and_delete_are_wired(client, monkeypatch):
    import app.main as main

    client.post("/api/seed", json={"scenario": "decline", "days": 20})
    main.app.dependency_overrides[main.get_authenticated_user] = (
        lambda: settings.DEFAULT_USER
    )
    monkeypatch.setattr(
        main,
        "bigquery_sync",
        lambda user_id, entries, timeline: {
            "enabled": True, "synced": len(timeline),
            "table_id": "demo.aura.daily", "privacy": analytics.PRIVACY_CONTRACT,
        },
    )
    monkeypatch.setattr(
        main,
        "bigquery_summary",
        lambda user_id: {
            "enabled": True, "available": True,
            "personal": {"daily_records": 20},
            "cohort": {"available": False},
        },
    )
    monkeypatch.setattr(
        main, "bigquery_delete",
        lambda user_id: {"deleted": 20, "table_id": "demo.aura.daily"},
    )
    try:
        synced = client.post(
            "/api/analytics/bigquery/sync", json={"consent": True}
        )
        assert synced.status_code == 200
        assert synced.json()["synced"] == 20
        summary = client.get("/api/analytics/bigquery/summary")
        assert summary.status_code == 200
        assert summary.json()["personal"]["daily_records"] == 20
        deleted = client.delete("/api/analytics/bigquery/data")
        assert deleted.status_code == 200
        assert deleted.json()["deleted"] == 20
    finally:
        main.app.dependency_overrides.pop(main.get_authenticated_user, None)
