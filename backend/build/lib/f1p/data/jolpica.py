"""Jolpica (Ergast-compatible) API client with disk caching, throttling and parsers.

Rate limits: ~1 request/s sustained (faster bursts get 429s) and 500 requests/hour.
Completed seasons are cached forever; the current season is re-fetched once the cache is older
than ``CURRENT_SEASON_TTL``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

from f1p import config

log = logging.getLogger(__name__)

PAGE_LIMIT = 100
MIN_INTERVAL_S = 1.0
CURRENT_SEASON_TTL = timedelta(hours=1)

_last_request = 0.0


def _cache_path(path: str, params: dict) -> Path:
    key = hashlib.sha1(json.dumps([path, sorted(params.items())]).encode()).hexdigest()[:16]
    return config.JOLPICA_CACHE_DIR / f"{path.strip('/').replace('/', '_')}_{key}.json"


def _get(path: str, params: dict, ttl: timedelta | None) -> dict:
    global _last_request
    cache = _cache_path(path, params)
    if cache.exists():
        age = time.time() - cache.stat().st_mtime
        if ttl is None or age < ttl.total_seconds():
            return json.loads(cache.read_text(encoding="utf-8"))

    url = f"{config.JOLPICA_BASE_URL}/{path.strip('/')}.json"
    for attempt in range(6):
        wait = MIN_INTERVAL_S - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code == 429 or resp.status_code >= 500:
            backoff = int(resp.headers.get("Retry-After", 0)) or 5 * 2**attempt
            log.warning("Jolpica %s on %s, retrying in %ss", resp.status_code, url, backoff)
            time.sleep(backoff)
            continue
        resp.raise_for_status()
        data = resp.json()
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(data), encoding="utf-8")
        return data
    raise RuntimeError(f"Jolpica request failed after retries: {url}")


def _ttl_for(season: int) -> timedelta | None:
    return CURRENT_SEASON_TTL if season >= datetime.now(timezone.utc).year else None


def _get_races_paginated(path: str, season: int) -> list[dict]:
    """Fetch every page of a race-table endpoint and merge results split across pages."""
    ttl = _ttl_for(season)
    merged: dict[str, dict] = {}
    offset = 0
    while True:
        data = _get(path, {"limit": PAGE_LIMIT, "offset": offset}, ttl)["MRData"]
        for race in data["RaceTable"]["Races"]:
            key = race["round"]
            if key not in merged:
                merged[key] = race
            else:
                # A race's rows can straddle a page boundary.
                for list_key in ("Results", "QualifyingResults", "SprintResults"):
                    if list_key in race:
                        merged[key].setdefault(list_key, []).extend(race[list_key])
        offset += PAGE_LIMIT
        if offset >= int(data["total"]):
            break
    return sorted(merged.values(), key=lambda r: int(r["round"]))


def fetch_schedule(season: int) -> list[dict]:
    return _get(f"{season}", {"limit": PAGE_LIMIT}, _ttl_for(season))["MRData"]["RaceTable"][
        "Races"
    ]


def fetch_results(season: int) -> list[dict]:
    return _get_races_paginated(f"{season}/results", season)


def fetch_sprint_results(season: int) -> list[dict]:
    return _get_races_paginated(f"{season}/sprint", season)


def fetch_qualifying(season: int) -> list[dict]:
    return _get_races_paginated(f"{season}/qualifying", season)


# ---------------------------------------------------------------- parsers (pure functions)


def race_id(season: int | str, round_: int | str) -> str:
    return f"{int(season)}-{int(round_)}"


def _to_int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _utc(d: str | None, t: str | None) -> datetime | None:
    """Combine Jolpica date + time strings into a naive UTC datetime."""
    if not d or not t:
        return None
    return datetime.fromisoformat(f"{d}T{t.rstrip('Z')}")


def lap_time_to_seconds(text: str | None) -> float | None:
    """'1:36.477' -> 96.477; '58.123' -> 58.123; missing -> None."""
    if not text:
        return None
    try:
        if ":" in text:
            minutes, seconds = text.split(":", 1)
            return int(minutes) * 60 + float(seconds)
        return float(text)
    except ValueError:
        return None


def parse_race(race: dict) -> dict:
    circuit = race["Circuit"]
    loc = circuit.get("Location", {})
    quali = race.get("Qualifying", {})
    sprint = race.get("Sprint", {})
    return {
        "id": race_id(race["season"], race["round"]),
        "season": int(race["season"]),
        "round": int(race["round"]),
        "name": race["raceName"],
        "circuit_id": circuit["circuitId"],
        "circuit_name": circuit["circuitName"],
        "locality": loc.get("locality"),
        "country": loc.get("country"),
        "race_date": date.fromisoformat(race["date"]),
        "race_start_utc": _utc(race["date"], race.get("time")),
        "quali_start_utc": _utc(quali.get("date"), quali.get("time")),
        "sprint_start_utc": _utc(sprint.get("date"), sprint.get("time")),
        "weekend_format": "sprint" if "Sprint" in race else "conventional",
    }


def parse_driver(d: dict) -> dict:
    dob = d.get("dateOfBirth")
    return {
        "id": d["driverId"],
        "code": d.get("code"),
        "permanent_number": _to_int(d.get("permanentNumber")),
        "given_name": d["givenName"],
        "family_name": d["familyName"],
        "date_of_birth": date.fromisoformat(dob) if dob else None,
        "nationality": d.get("nationality"),
    }


def parse_constructor(c: dict) -> dict:
    return {"id": c["constructorId"], "name": c["name"], "nationality": c.get("nationality")}


def parse_result_rows(race: dict, session: str) -> list[dict]:
    """Rows for ``results`` from a race's ``Results`` (session R) or ``SprintResults`` (S)."""
    key = "Results" if session == "R" else "SprintResults"
    rid = race_id(race["season"], race["round"])
    rows = []
    for order, r in enumerate(race.get(key, []), start=1):
        position_text = r["positionText"]
        classified = position_text.isdigit()
        rows.append(
            {
                "race_id": rid,
                "session": session,
                "driver_id": r["Driver"]["driverId"],
                "constructor_id": r["Constructor"]["constructorId"],
                "car_number": _to_int(r.get("number")),
                "grid": _to_int(r.get("grid")),
                "position": int(position_text) if classified else None,
                "position_text": position_text,
                "position_order": _to_int(r.get("position")) or order,
                "points": float(r.get("points", 0)),
                "laps": _to_int(r.get("laps")),
                "status": r.get("status", ""),
                "time_ms": _to_int(r.get("Time", {}).get("millis")),
                "classified": classified,
                "source": "jolpica",
            }
        )
    return rows


def parse_qualifying_rows(race: dict) -> list[dict]:
    rid = race_id(race["season"], race["round"])
    return [
        {
            "race_id": rid,
            "driver_id": q["Driver"]["driverId"],
            "constructor_id": q["Constructor"]["constructorId"],
            "position": int(q["position"]),
            "q1_s": lap_time_to_seconds(q.get("Q1")),
            "q2_s": lap_time_to_seconds(q.get("Q2")),
            "q3_s": lap_time_to_seconds(q.get("Q3")),
            "source": "jolpica",
        }
        for q in race.get("QualifyingResults", [])
    ]
