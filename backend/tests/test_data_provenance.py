"""Tests that synthetic demo records cannot contaminate real cohort analytics."""


def test_seeded_entries_are_marked_synthetic(client):
    client.post("/api/seed", json={"scenario": "decline", "days": 20})
    entries = client.get("/api/entries").json()["entries"]
    assert entries
    assert {entry["source"] for entry in entries} == {"synthetic_demo"}


def test_manual_entry_is_marked_user_data(client):
    client.post("/api/entries", json={
        "date": "2026-01-01",
        "journal_text": "A regular check-in",
        "sleep_hours": 7,
        "social_count": 3,
        "energy": 4,
    })
    entries = client.get("/api/entries").json()["entries"]
    assert entries[0]["source"] == "user"
