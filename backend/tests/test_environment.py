"""Tests for seasonal/daylight correlation (Feature 4).

Network is stubbed so tests are deterministic and offline.
"""
from datetime import date, timedelta

import pytest

from app import environment


def _timeline(indices, start=None):
    start = start or (date.today() - timedelta(days=len(indices) - 1))
    return [
        {"date": (start + timedelta(days=i)).isoformat(),
         "aura_index": v, "calibrating": False}
        for i, v in enumerate(indices)
    ]


def test_pearson_basic():
    # Perfect negative correlation.
    r = environment._pearson([1, 2, 3, 4], [4, 3, 2, 1])
    assert r is not None and round(r, 3) == -1.0


def test_interpret_bands():
    assert "seasonal pattern" in environment._interpret(-0.6)
    assert "No strong" in environment._interpret(0.0)


def test_correlate_needs_data(monkeypatch):
    monkeypatch.setattr(environment, "_fetch_daylight", lambda *a, **k: {})
    out = environment.correlate(_timeline([10, 20, 30]))
    assert out["available"] is False


def test_correlate_with_stubbed_daylight(monkeypatch):
    tl = _timeline([10, 20, 30, 40, 50, 60, 70])

    def fake_fetch(lat, lon, start, end):
        # Daylight falls as the index rises -> strong negative correlation.
        return {d["date"]: 14.0 - i * 0.5 for i, d in enumerate(tl)}

    monkeypatch.setattr(environment, "_fetch_daylight", fake_fetch)
    out = environment.correlate(tl, lat=43.6, lon=-79.4)
    assert out["available"] is True
    assert out["correlation"] < -0.4
    assert out["location_is_default"] is False
    assert len(out["series"]) == len(tl)


def test_correlate_network_failure(monkeypatch):
    monkeypatch.setattr(environment, "_fetch_daylight", lambda *a, **k: None)
    out = environment.correlate(_timeline([10, 20, 30, 40, 50, 60]))
    assert out["available"] is False


def test_environment_endpoint(client, monkeypatch):
    client.post("/api/seed", json={"scenario": "decline", "days": 60})
    # Stub network for the endpoint too.
    monkeypatch.setattr(
        environment, "_fetch_daylight",
        lambda lat, lon, start, end: {
            (date.today() - timedelta(days=i)).isoformat(): 12.0 - i * 0.02
            for i in range(60)
        },
    )
    r = client.get("/api/environment")
    assert r.status_code == 200
    # Either correlated or gracefully unavailable, but never a 500.
    assert "available" in r.json()
