"""
API endpoints to seed countries, states, and cities from GitHub dataset.
POST /api/admin/seed/geo        — trigger import (background task)
GET  /api/admin/seed/geo/status — poll job progress
"""

import logging
import threading
import time
from typing import List, Optional

import requests
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.modules.common.auth import require_any_permission
from app.modules.users.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/seed/geo", tags=["Geo Seed"])

# Primary: GitHub raw JSON (all data in one download, no rate limit)
GITHUB_URL = (
    "https://raw.githubusercontent.com/dr5hn/countries-states-cities-database"
    "/master/json/countries%2Bstates%2Bcities.json"
)

# Fallback: countrystatecity.in API (key from COUNTRY_STATE_CITY_API_KEY env var)
API_KEY = settings.COUNTRY_STATE_CITY_API_KEY
API_BASE = "https://api.countrystatecity.in/v1"
API_HEADERS = {"X-CSCAPI-KEY": API_KEY}
REQUEST_DELAY = 2.0
_MAX_RETRIES = 4

_job: dict = {
    "running": False,
    "done": False,
    "error": None,
    "total": 0,
    "processed": 0,
    "current": "",
    "countries_added": 0,
    "states_added": 0,
    "cities_added": 0,
}
_lock = threading.Lock()


def _api_get(url: str) -> list:
    delay = 10
    for attempt in range(_MAX_RETRIES):
        resp = requests.get(url, headers=API_HEADERS, timeout=20)
        if resp.status_code == 429:
            time.sleep(delay * (2 ** attempt))
            continue
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []
    raise Exception(f"Rate limit max retries exceeded for {url}")


def _upsert_country(conn, name: str, iso2: str, phone: str, currency: str) -> int | None:
    if not name or not iso2:
        return None
    row = conn.execute(text("SELECT id FROM countries WHERE country_code=:c"), {"c": iso2}).fetchone()
    if row:
        conn.execute(
            text("UPDATE countries SET country_name=:n, phone_code=:p, currency_code=:cu WHERE country_code=:c"),
            {"n": name, "p": phone, "cu": currency, "c": iso2},
        )
        return row[0]
    conn.execute(
        text("INSERT INTO countries (country_name, country_code, phone_code, currency_code, status) "
             "VALUES (:n, :c, :p, :cu, 'active')"),
        {"n": name, "c": iso2, "p": phone, "cu": currency},
    )
    with _lock:
        _job["countries_added"] += 1
    row = conn.execute(text("SELECT id FROM countries WHERE country_code=:c"), {"c": iso2}).fetchone()
    return row[0] if row else None


def _upsert_state(conn, country_id: int, name: str, code: str) -> int | None:
    if not name:
        return None
    row = conn.execute(
        text("SELECT id FROM states WHERE country_id=:cid AND state_name=:n"),
        {"cid": country_id, "n": name},
    ).fetchone()
    if row:
        conn.execute(text("UPDATE states SET state_code=:sc WHERE id=:id"), {"sc": code, "id": row[0]})
        return row[0]
    conn.execute(
        text("INSERT INTO states (country_id, state_name, state_code, status) VALUES (:cid, :n, :sc, 'active')"),
        {"cid": country_id, "n": name, "sc": code},
    )
    with _lock:
        _job["states_added"] += 1
    row = conn.execute(
        text("SELECT id FROM states WHERE country_id=:cid AND state_name=:n"),
        {"cid": country_id, "n": name},
    ).fetchone()
    return row[0] if row else None


def _upsert_city(conn, country_id: int, state_id: int, name: str) -> None:
    if not name:
        return
    exists = conn.execute(
        text("SELECT 1 FROM cities WHERE country_id=:cid AND state_id=:sid AND city_name=:n"),
        {"cid": country_id, "sid": state_id, "n": name},
    ).fetchone()
    if not exists:
        conn.execute(
            text("INSERT INTO cities (country_id, state_id, city_name, status) VALUES (:cid, :sid, :n, 'active')"),
            {"cid": country_id, "sid": state_id, "n": name},
        )
        with _lock:
            _job["cities_added"] += 1


def _run_github(conn, country_codes: set, include_cities: bool) -> None:
    with _lock:
        _job["current"] = "Downloading dataset from GitHub..."

    resp = requests.get(GITHUB_URL, timeout=120)
    resp.raise_for_status()
    dataset = resp.json()

    if country_codes:
        dataset = [c for c in dataset if (c.get("iso2") or "").upper() in country_codes]

    with _lock:
        _job["total"] = len(dataset)

    for i, c in enumerate(dataset, 1):
        name = (c.get("name") or "").strip()
        iso2 = (c.get("iso2") or "").strip()

        with _lock:
            _job["current"] = f"{name} ({iso2})"
            _job["processed"] = i

        country_id = _upsert_country(
            conn, name, iso2,
            str(c.get("phone_code") or ""),
            c.get("currency") or "",
        )
        if not country_id:
            continue

        for s in c.get("states") or []:
            s_name = (s.get("name") or "").strip()
            s_code = (s.get("state_code") or "").strip()
            state_id = _upsert_state(conn, country_id, s_name, s_code)
            if not state_id:
                continue
            if include_cities:
                for city in s.get("cities") or []:
                    _upsert_city(conn, country_id, state_id, (city.get("name") or "").strip())

        conn.commit()


def _run_import(country_codes: list[str], include_cities: bool) -> None:
    codes = {c.upper() for c in country_codes}

    with _lock:
        _job.update({
            "running": True, "done": False, "error": None,
            "total": 0, "processed": 0, "current": "Starting...",
            "countries_added": 0, "states_added": 0, "cities_added": 0,
        })

    try:
        with engine.connect() as conn:
            try:
                _run_github(conn, codes, include_cities)
            except Exception as gh_err:
                logger.warning("GitHub source failed (%s), falling back to API", gh_err)
                with _lock:
                    _job["current"] = "GitHub failed, switching to API..."
                # API fallback: re-fetch country list then states/cities
                all_countries = _api_get(f"{API_BASE}/countries")
                time.sleep(REQUEST_DELAY)
                if codes:
                    all_countries = [c for c in all_countries if (c.get("iso2") or "").upper() in codes]
                with _lock:
                    _job["total"] = len(all_countries)
                for i, c_data in enumerate(all_countries, 1):
                    name = (c_data.get("name") or "").strip()
                    iso2 = (c_data.get("iso2") or "").strip()
                    with _lock:
                        _job["current"] = f"{name} ({iso2})"
                        _job["processed"] = i
                    country_id = _upsert_country(
                        conn, name, iso2,
                        str(c_data.get("phonecode") or ""),
                        c_data.get("currency") or "",
                    )
                    if not country_id:
                        continue
                    try:
                        states_data = _api_get(f"{API_BASE}/countries/{iso2}/states")
                        time.sleep(REQUEST_DELAY)
                    except Exception:
                        conn.commit()
                        continue
                    for s_data in states_data:
                        s_name = (s_data.get("name") or "").strip()
                        s_code = (s_data.get("iso2") or "").strip()
                        state_id = _upsert_state(conn, country_id, s_name, s_code)
                        if not state_id or not include_cities or not s_code:
                            continue
                        try:
                            cities_data = _api_get(
                                f"{API_BASE}/countries/{iso2}/states/{s_code}/cities"
                            )
                            time.sleep(REQUEST_DELAY)
                        except Exception:
                            continue
                        for city_data in cities_data:
                            _upsert_city(conn, country_id, state_id,
                                         (city_data.get("name") or "").strip())
                    conn.commit()

        with _lock:
            _job.update({"running": False, "done": True, "current": "Completed"})

    except Exception as e:
        logger.exception("Geo seed failed: %s", e)
        with _lock:
            _job.update({"running": False, "done": True, "error": str(e), "current": "Failed"})


@router.post("")
def trigger_geo_seed(
    background_tasks: BackgroundTasks,
    countries: Optional[List[str]] = Query(
        default=None,
        description="ISO2 codes to import. Omit for all 250 countries.",
    ),
    include_cities: bool = Query(
        default=False,
        description="Also import cities for each state.",
    ),
    current_user: User = Depends(require_any_permission("settings.create")),
):
    """
    Trigger geo data import in the background.
    Downloads from GitHub (one request, no rate limit). Idempotent.
    """
    with _lock:
        if _job["running"]:
            return {
                "status": "already_running",
                "message": "A geo import is already in progress.",
                "job": dict(_job),
            }

    background_tasks.add_task(_run_import, countries or [], include_cities)
    return {
        "status": "started",
        "message": "Geo data import started in background.",
        "params": {"countries": countries, "include_cities": include_cities},
    }


@router.get("/status")
def geo_seed_status(_: User = Depends(require_any_permission("settings.view"))):
    """Returns status of the current or last geo import job."""
    with _lock:
        return {"status": "success", "job": dict(_job)}
