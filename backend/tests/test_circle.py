"""Tests for the Circle of Care (opt-in trusted contacts + nudges)."""
from app import circle


def test_no_nudge_below_tier_2():
    contacts = [{"id": 1, "name": "Sam", "notify_tier": 2}]
    assert circle.build_nudge(0, contacts) is None
    assert circle.build_nudge(1, contacts) is None


def test_no_nudge_without_contacts():
    assert circle.build_nudge(3, []) is None


def test_nudge_respects_notify_tier():
    contacts = [{"id": 1, "name": "Sam", "notify_tier": 3}]
    # Contact only wants tier-3 nudges; tier 2 should yield nothing.
    assert circle.build_nudge(2, contacts) is None
    nudge = circle.build_nudge(3, contacts)
    assert nudge is not None
    assert nudge["contacts"][0]["name"] == "Sam"
    # Message is generic and never contains scores / data.
    msg = nudge["contacts"][0]["message"]
    assert "Sam" in msg
    assert "index" not in msg.lower()
    assert "score" not in msg.lower()


def test_nudge_privacy_note_present():
    contacts = [{"id": 1, "name": "Alex", "notify_tier": 2}]
    nudge = circle.build_nudge(2, contacts)
    assert "never" in nudge["privacy_note"].lower()


# --- API-level tests --------------------------------------------------------
def test_contacts_crud(client):
    # Create
    r = client.post("/api/contacts", json={
        "name": "Jordan", "method": "text", "detail": "555-0100",
        "notify_tier": 3,
    })
    assert r.status_code == 200
    cid = r.json()["id"]

    # List
    lst = client.get("/api/contacts").json()["contacts"]
    assert any(c["name"] == "Jordan" for c in lst)

    # Delete
    d = client.delete(f"/api/contacts/{cid}").json()
    assert d["deleted"] == 1
    lst2 = client.get("/api/contacts").json()["contacts"]
    assert not any(c["name"] == "Jordan" for c in lst2)


def test_circle_nudge_surfaces_at_urgent_tier(client):
    client.post("/api/contacts", json={
        "name": "Riley", "method": "phone", "detail": "", "notify_tier": 2,
    })
    # A crisis entry forces tier 3 -> nudge should appear in status.
    client.post("/api/entries", json={
        "journal_text": "I can't go on and feel worthless",
        "sleep_hours": 3, "social_count": 0, "energy": 1,
    })
    s = client.get("/api/status").json()
    assert s["tier"] == 3
    assert s["circle_nudge"] is not None
    assert any(c["name"] == "Riley" for c in s["circle_nudge"]["contacts"])


def test_wipe_clears_contacts(client):
    client.post("/api/contacts", json={
        "name": "Casey", "method": "email", "detail": "c@example.com",
        "notify_tier": 3,
    })
    client.delete("/api/data")
    assert client.get("/api/contacts").json()["contacts"] == []
