"""Passive signal integration: wearables (Google Fit) and phone sensors.

Two goals from the product brief:
  * reduce manual entry / increase data reliability by pulling sleep + activity
    from a wearable (Google Fit), and
  * derive *passive* behavioral signals from the phone (screen time), which are
    known digital-phenotyping markers, without being invasive (we never read
    message content -- only aggregate daily counts).

Real Google Fit access is an OAuth2 flow returning an access token; the REST
call is documented in ``fetch_google_fit``. Because a live OAuth handshake is
not available in the demo/hackathon environment, ``simulate_fit`` produces
realistic, reproducible data aligned to the user's existing timeline so the
end-to-end passive pipeline can be demonstrated and tested deterministically.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

# Google Fit aggregate data-source identifiers (used by the real REST call).
FIT_STEPS_SOURCE = "derived:com.google.step_count.delta:com.google.android.gms:estimated_steps"
FIT_ACTIVE_SOURCE = "derived:com.google.active_minutes:com.google.android.gms:merge_active_minutes"
FIT_SLEEP_SOURCE = "derived:com.google.sleep.segment:com.google.android.gms:merged"


def fetch_google_fit(access_token: str, days: int) -> list[dict] | None:  # pragma: no cover - needs live OAuth
    """Fetch daily steps / active minutes / sleep from the Google Fit REST API.

    Returns a list of ``{date, steps, active_minutes, sleep_hours}`` or None on
    any failure (caller then falls back to simulation / manual entry).

    This is intentionally isolated and lazily-imported so the dependency and
    network call never affect the offline path.
    """
    if not access_token:
        return None
    try:
        import time

        import requests  # provided transitively by google deps

        now_ms = int(time.time() * 1000)
        start_ms = now_ms - days * 86_400_000
        body = {
            "aggregateBy": [
                {"dataTypeName": "com.google.step_count.delta"},
                {"dataTypeName": "com.google.active_minutes"},
            ],
            "bucketByTime": {"durationMillis": 86_400_000},
            "startTimeMillis": start_ms,
            "endTimeMillis": now_ms,
        }
        resp = requests.post(
            "https://www.googleapis.com/fitness/v1/users/me/dataset:aggregate",
            headers={"Authorization": f"Bearer {access_token}"},
            json=body,
            timeout=15,
        )
        resp.raise_for_status()
        out: list[dict] = []
        for i, bucket in enumerate(resp.json().get("bucket", [])):
            d = date.fromtimestamp(int(bucket["startTimeMillis"]) / 1000)
            steps = active = 0
            for ds in bucket.get("dataset", []):
                for pt in ds.get("point", []):
                    for val in pt.get("value", []):
                        n = val.get("intVal") or val.get("fpVal") or 0
                        if "step_count" in ds.get("dataSourceId", ""):
                            steps += int(n)
                        elif "active_minutes" in ds.get("dataSourceId", ""):
                            active += int(n)
            out.append({"date": d.isoformat(), "steps": steps,
                        "active_minutes": active, "sleep_hours": None})
        return out
    except Exception:
        return None


def simulate_fit(entries: list[dict], days: int) -> list[dict]:
    """Produce realistic passive data aligned to existing entries.

    Activity correlates with the user's self-reported energy and sleep so the
    simulated wearable data tells the same behavioral story (lower activity and
    higher late-night screen time as things decline). Deterministic per date.
    """
    recent = entries[-days:] if days < len(entries) else entries
    out: list[dict] = []
    for e in recent:
        # Seed per-date so results are stable/reproducible.
        rng = random.Random(hash(e["date"]) & 0xFFFFFFFF)
        energy = e.get("energy") or 3
        sleep = e.get("sleep_hours") or 7.0
        social = e.get("social_count")
        social = 3 if social is None else social

        # Higher energy -> more steps & active minutes.
        base_steps = 1500 + energy * 1500 + social * 300
        steps = max(200, int(rng.gauss(base_steps, 900)))
        active = max(0, int(rng.gauss(8 + energy * 9, 12)))

        # Screen time rises as sleep and energy fall (rumination / doomscroll).
        screen = int(rng.gauss(240 + (7.0 - sleep) * 40 + (5 - energy) * 25, 40))
        screen = max(30, min(900, screen))

        out.append({
            "date": e["date"],
            "steps": steps,
            "active_minutes": active,
            "screen_time_min": screen,
            "sleep_hours": e.get("sleep_hours"),
        })
    return out


def sync_passive(
    entries: list[dict], *, days: int, access_token: str | None = None,
) -> tuple[list[dict], str]:
    """Return (passive_rows, source). Tries live Google Fit, else simulates.

    ``passive_rows`` are ``{date, steps, active_minutes, screen_time_min}``.
    ``source`` is 'google_fit' or 'simulated' for transparency in the UI.
    """
    if access_token:
        fit = fetch_google_fit(access_token, days)
        if fit:
            # Fit doesn't provide phone screen time; fill it from simulation.
            sim = {r["date"]: r for r in simulate_fit(entries, days)}
            for row in fit:
                row["screen_time_min"] = sim.get(
                    row["date"], {}).get("screen_time_min")
            return fit, "google_fit"
    return simulate_fit(entries, days), "simulated"
