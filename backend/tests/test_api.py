def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["gemini_enabled"] is False  # forced offline in tests


def test_seed_status_timeline(client):
    r = client.post("/api/seed", json={"scenario": "decline", "days": 60})
    assert r.status_code == 200
    assert r.json()["entry_count"] == 60

    s = client.get("/api/status").json()
    assert s["has_data"] is True
    assert s["tier"] is not None

    tl = client.get("/api/timeline").json()
    assert len(tl["timeline"]) == 60
    assert any(sig["key"] == "future_focus_ratio" for sig in tl["signals"])


def test_crisis_entry_forces_tier3(client):
    r = client.post("/api/entries", json={
        "journal_text": "I want to die, there is no reason to live",
        "sleep_hours": 3, "social_count": 0, "energy": 1,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["safety_alert"] is True
    assert body["tier"] == 3


def test_assessment_schema_and_submit(client):
    schema = client.get("/api/assessments/schema").json()
    assert len(schema["instruments"]["PHQ-9"]["items"]) == 9

    r = client.post("/api/assessments", json={
        "instrument": "PHQ-9", "responses": [2] * 9,
    })
    body = r.json()
    assert body["total"] == 18
    assert body["severity"] == "moderately severe"
    assert body["safety_alert"] is True  # item 9 endorsed


def test_eval_after_seed(client):
    client.post("/api/seed", json={"scenario": "decline", "days": 60})
    ev = client.get("/api/eval").json()
    assert ev["available"] is True
    assert ev["correlation"]["PHQ-9"] is not None


def test_wipe_clears_data(client):
    client.post("/api/seed", json={"scenario": "decline", "days": 30})
    d = client.delete("/api/data").json()
    assert d["deleted"] > 0
    assert client.get("/api/status").json()["has_data"] is False
