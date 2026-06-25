"""
Import countries, states, and cities into the database.

Sources (tried in order):
  1. GitHub raw JSON (dr5hn/countries-states-cities-database) — one download, no rate limit
  2. countrystatecity.in API — fallback, subject to daily quota

Usage (run from backend/ directory):
    python scripts/import_geo_data.py                    # all countries + states + cities
    python scripts/import_geo_data.py --countries IN AE  # specific ISO2 codes
    python scripts/import_geo_data.py --no-cities        # skip cities
    python scripts/import_geo_data.py --api              # force API source
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from sqlalchemy import text

from app.database import engine

# ── GitHub source (full dataset, single download) ──────────────────────────
GITHUB_URL = (
    "https://raw.githubusercontent.com/dr5hn/countries-states-cities-database"
    "/master/json/countries%2Bstates%2Bcities.json"
)

# ── countrystatecity.in API (fallback) ─────────────────────────────────────
API_KEY = "f6c58fbdd3e3f46cf81314046643f09177099cfdb07b772af82a6cf31650de14"
API_BASE = "https://api.countrystatecity.in/v1"
API_HEADERS = {"X-CSCAPI-KEY": API_KEY}
REQUEST_DELAY = 2.0
MAX_RETRIES = 4


def api_get(url: str) -> list:
    delay = 10
    for attempt in range(MAX_RETRIES):
        resp = requests.get(url, headers=API_HEADERS, timeout=20)
        if resp.status_code == 429:
            wait = delay * (2 ** attempt)
            print(f" [rate-limited, waiting {wait}s]", end="", flush=True)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []
    raise Exception(f"Rate limit max retries exceeded for {url}")


# ── Database helpers ────────────────────────────────────────────────────────

def upsert_country(conn, name: str, iso2: str, phone: str, currency: str) -> int | None:
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
    row = conn.execute(text("SELECT id FROM countries WHERE country_code=:c"), {"c": iso2}).fetchone()
    return row[0] if row else None


def upsert_state(conn, country_id: int, name: str, code: str) -> int | None:
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
    row = conn.execute(
        text("SELECT id FROM states WHERE country_id=:cid AND state_name=:n"),
        {"cid": country_id, "n": name},
    ).fetchone()
    return row[0] if row else None


def upsert_city(conn, country_id: int, state_id: int, name: str) -> bool:
    if not name:
        return False
    exists = conn.execute(
        text("SELECT 1 FROM cities WHERE country_id=:cid AND state_id=:sid AND city_name=:n"),
        {"cid": country_id, "sid": state_id, "n": name},
    ).fetchone()
    if not exists:
        conn.execute(
            text("INSERT INTO cities (country_id, state_id, city_name, status) VALUES (:cid, :sid, :n, 'active')"),
            {"cid": country_id, "sid": state_id, "n": name},
        )
        return True
    return False


# ── GitHub source ───────────────────────────────────────────────────────────

def import_from_github(conn, country_codes: set, include_cities: bool) -> None:
    print("Downloading full dataset from GitHub...", flush=True)
    resp = requests.get(GITHUB_URL, timeout=120)
    resp.raise_for_status()
    dataset = resp.json()
    print(f"Downloaded. {len(dataset)} countries in dataset.", flush=True)

    if country_codes:
        dataset = [c for c in dataset if (c.get("iso2") or "").upper() in country_codes]
        print(f"Filtered to {len(dataset)} countries.")

    total = len(dataset)
    countries_added = states_added = cities_added = 0

    for i, c in enumerate(dataset, 1):
        name = (c.get("name") or "").strip()
        iso2 = (c.get("iso2") or "").strip()
        phone = str(c.get("phone_code") or "").strip()
        currency = (c.get("currency") or "").strip()

        print(f"[{i}/{total}] {name} ({iso2})", end="", flush=True)

        country_id = upsert_country(conn, name, iso2, phone, currency)
        if not country_id:
            print(" [skipped]")
            continue
        if not conn.execute(text("SELECT id FROM countries WHERE country_code=:c"), {"c": iso2}).fetchone():
            countries_added += 1

        states_data = c.get("states") or []
        sc = 0
        cc = 0
        for s in states_data:
            s_name = (s.get("name") or "").strip()
            s_code = (s.get("state_code") or "").strip()
            state_id = upsert_state(conn, country_id, s_name, s_code)
            if not state_id:
                continue
            sc += 1
            states_added += 1

            if include_cities:
                for city in s.get("cities") or []:
                    c_name = (city.get("name") or "").strip()
                    if upsert_city(conn, country_id, state_id, c_name):
                        cc += 1
                        cities_added += 1

        conn.commit()
        print(f"  {sc} states, {cc} cities")

    print(f"\nSummary: {countries_added} new countries, {states_added} new states, {cities_added} new cities.")


# ── API source (fallback) ───────────────────────────────────────────────────

def import_from_api(conn, country_codes: set, include_cities: bool) -> None:
    print("Fetching country list from API...")
    all_countries = api_get(f"{API_BASE}/countries")
    time.sleep(REQUEST_DELAY)
    print(f"Found {len(all_countries)} countries.")

    if country_codes:
        all_countries = [c for c in all_countries if (c.get("iso2") or "").upper() in country_codes]
        print(f"Filtered to {len(all_countries)} countries.")

    total = len(all_countries)
    for i, c_data in enumerate(all_countries, 1):
        name = (c_data.get("name") or "").strip()
        iso2 = (c_data.get("iso2") or "").strip()
        print(f"[{i}/{total}]  > {name} ({iso2})", end="", flush=True)

        country_id = upsert_country(
            conn, name, iso2,
            str(c_data.get("phonecode") or ""),
            c_data.get("currency") or "",
        )
        if not country_id:
            print(" [skipped]")
            continue

        try:
            states_data = api_get(f"{API_BASE}/countries/{iso2}/states")
            time.sleep(REQUEST_DELAY)
        except Exception as e:
            conn.commit()
            print(f" [states error: {e}]")
            continue

        sc = cc = 0
        for s_data in states_data:
            s_name = (s_data.get("name") or "").strip()
            s_code = (s_data.get("iso2") or "").strip()
            state_id = upsert_state(conn, country_id, s_name, s_code)
            if not state_id:
                continue
            sc += 1

            if include_cities:
                if not s_code:
                    continue
                try:
                    cities_data = api_get(f"{API_BASE}/countries/{iso2}/states/{s_code}/cities")
                    time.sleep(REQUEST_DELAY)
                except Exception:
                    continue
                for city_data in cities_data:
                    c_name = (city_data.get("name") or "").strip()
                    if upsert_city(conn, country_id, state_id, c_name):
                        cc += 1

        conn.commit()
        print(f"  {sc} states, {cc} cities")


# ── Entry point ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--countries", nargs="*", help="ISO2 codes (default: all)")
    parser.add_argument("--no-cities", action="store_true", help="Skip city import")
    parser.add_argument("--api", action="store_true", help="Force countrystatecity.in API instead of GitHub")
    args = parser.parse_args()

    codes = {c.upper() for c in (args.countries or [])}
    include_cities = not args.no_cities

    with engine.connect() as conn:
        if args.api:
            import_from_api(conn, codes, include_cities)
        else:
            try:
                import_from_github(conn, codes, include_cities)
            except Exception as e:
                print(f"GitHub source failed ({e}), falling back to API...")
                import_from_api(conn, codes, include_cities)

    print("Done.")


if __name__ == "__main__":
    main()
