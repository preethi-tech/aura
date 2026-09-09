"""Seasonal & environmental context correlation.

Seasonal / daylight-linked mood changes are common but usually go unrecognised
by the person experiencing them -- they blame themselves ("something's wrong
with me") rather than seeing a predictable, external, cyclical pattern. Naming
a dip as seasonal is both less stigmatising and more actionable, and stops the
baseline engine from flagging the same yearly dip as a fresh anomaly.

We correlate the Aura Index against *free* public daylight data from Open-Meteo
(no API key, no billing). Location is optional and coarse (city-level) to
preserve privacy. Uses only the standard library so it runs anywhere, and
degrades gracefully (available=False) if the network is unavailable.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

# A neutral default demo location (Toronto) with clear seasonal daylight swing.
# Real deployments pass the user's coarse lat/lon; this only powers the demo.
DEFAULT_LAT = 43.65
DEFAULT_LON = -79.38

_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 4:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / ((sxx * syy) ** 0.5)


def _query(base_url: str, lat: float, lon: float, start: str,
           end: str) -> dict[str, float]:
    """Query one Open-Meteo endpoint for daily daylight hours. Best-effort:
    returns {} on any failure so callers can merge multiple sources."""
    params = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon,
        "daily": "daylight_duration",
        "timezone": "auto",
        "start_date": start, "end_date": end,
    })
    try:
        req = urllib.request.Request(f"{base_url}?{params}",
                                     headers={"User-Agent": "aura/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        daily = data.get("daily", {})
        times = daily.get("time", [])
        secs = daily.get("daylight_duration", [])
        return {t: round(s / 3600.0, 2)
                for t, s in zip(times, secs) if s is not None}
    except Exception:
        return {}


def _fetch_daylight(lat: float, lon: float, start: str,
                    end: str) -> dict[str, float] | None:
    """Return {date: daylight_hours} from Open-Meteo, or None on total failure.

    Merges the historical *archive* API (covers older dates, ~5-day lag) with
    the *forecast* API (covers the last ~92 days through today) so the full
    window is filled regardless of how recent it is.
    """
    merged: dict[str, float] = {}
    merged.update(_query(_ARCHIVE_URL, lat, lon, start, end))
    merged.update(_query(_FORECAST_URL, lat, lon, start, end))
    return merged or None


def correlate(timeline: list[dict], *, lat: float | None = None,
              lon: float | None = None) -> dict:
    """Correlate the Aura Index with local daylight hours over the timeline."""
    scored = [d for d in timeline
              if d.get("aura_index") is not None and d.get("date")]
    if len(scored) < 6:
        return {"available": False,
                "reason": "Add more check-ins to reveal seasonal patterns."}

    used_default = lat is None or lon is None
    lat = DEFAULT_LAT if lat is None else lat
    lon = DEFAULT_LON if lon is None else lon

    start, end = scored[0]["date"], scored[-1]["date"]
    daylight = _fetch_daylight(lat, lon, start, end)
    if not daylight:
        return {"available": False,
                "reason": "Couldn't reach the daylight service right now."}

    xs, ys, series = [], [], []
    for d in scored:
        dl = daylight.get(d["date"])
        if dl is None:
            continue
        xs.append(dl)
        ys.append(float(d["aura_index"]))
        series.append({"date": d["date"], "daylight": dl,
                       "aura_index": d["aura_index"]})
    r = _pearson(xs, ys)
    if r is None:
        return {"available": False,
                "reason": "Not enough overlapping daylight data yet."}

    return {
        "available": True,
        "correlation": round(r, 2),
        "location_is_default": used_default,
        "daylight_range": [round(min(xs), 2), round(max(xs), 2)],
        "series": series,
        "interpretation": _interpret(r),
    }


def _interpret(r: float) -> str:
    if r <= -0.4:
        return ("Your index tends to rise as daylight shortens \u2014 a strong "
                "seasonal pattern. A dip here may be about the season, not you; "
                "morning light and routine can help.")
    if r <= -0.2:
        return ("There's a mild seasonal link \u2014 lower daylight lines up with "
                "a somewhat higher index. Worth keeping an eye on as seasons "
                "change.")
    if r >= 0.4:
        return ("Interesting \u2014 your index tends to ease as daylight shortens, "
                "the opposite of a typical seasonal pattern.")
    return "No strong seasonal pattern detected in your data so far."
