"""
API endpoints to seed countries, states, and cities from GeoNames
(geonames.org) - a free, public-domain geographic database distributed as
bulk dump files (no API key, no per-call rate limits, no paid tier).
POST /api/admin/seed/geo        - trigger import (background task)
GET  /api/admin/seed/geo/status - poll job progress
"""

import io
import logging
import threading
import time
import zipfile
from typing import List, Optional

import requests
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import text

from app.database import engine
from app.auth.permissions import require_any_permission
from app.models.users import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/seed/geo", tags=["Geo Seed"])

GEONAMES_DUMP_BASE = "https://download.geonames.org/export/dump"
COUNTRY_INFO_URL = f"{GEONAMES_DUMP_BASE}/countryInfo.txt"
ADMIN1_CODES_URL = f"{GEONAMES_DUMP_BASE}/admin1CodesASCII.txt"
# cities5000.zip = every populated place with population >= 5000, worldwide
# (~50k rows). GeoNames also publishes cities500/1000/15000 variants trading
# completeness for file size; 5000 is the practical default for launch
# markets without pulling in every hamlet.
CITIES_URL = f"{GEONAMES_DUMP_BASE}/cities5000.zip"

_MAX_RETRIES = 3
_RETRY_BACKOFF = 5  # seconds, multiplied by attempt number

_job: dict = {
    "running": False,
    "done": False,
    "error": None,
    "phase": 0,          # 1=countries, 2=states, 3=cities
    "phase_name": "",
    "total": 0,
    "processed": 0,
    "current": "",
    "countries_added": 0,
    "states_added": 0,
    "cities_added": 0,
}
_lock = threading.Lock()


def _fetch_text(url: str) -> str:
    last_error: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            last_error = e
            logger.warning("GeoNames fetch failed (attempt %s/%s) for %s: %s",
                           attempt + 1, _MAX_RETRIES, url, e)
            time.sleep(_RETRY_BACKOFF * (attempt + 1))
    raise RuntimeError(f"Could not download {url} after {_MAX_RETRIES} attempts: {last_error}")


def _fetch_cities_lines(url: str) -> list[str]:
    # The cities dump is tens of MB, so stream it in chunks rather than
    # buffering the whole response at once -- a stalled socket part-way
    # through an unstreamed download times out and loses the entire file.
    last_error: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            buf = io.BytesIO()
            with requests.get(url, timeout=(30, 120), stream=True) as resp:
                resp.raise_for_status()
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    if chunk:
                        buf.write(chunk)
            buf.seek(0)
            with zipfile.ZipFile(buf) as zf:
                # The zip holds exactly one .txt member matching its own
                # basename (e.g. cities5000.zip -> cities5000.txt).
                member = next(n for n in zf.namelist() if n.endswith(".txt"))
                return zf.read(member).decode("utf-8").splitlines()
        except (requests.RequestException, zipfile.BadZipFile) as e:
            last_error = e
            logger.warning("GeoNames cities download failed (attempt %s/%s): %s",
                           attempt + 1, _MAX_RETRIES, e)
            time.sleep(_RETRY_BACKOFF * (attempt + 1))
    raise RuntimeError(f"Could not download {url} after {_MAX_RETRIES} attempts: {last_error}")


def _normalize_phone(raw: str) -> str:
    """
    Most GeoNames phone values are a bare dialing code ("1", "44"), but a
    few list several in prose ("+1-809 and 1-829" for the Dominican
    Republic and Puerto Rico), which overflows countries.phone_code(10)
    and - because the whole country pass shares one transaction - used to
    abort the entire seed over two rows. Keep the first code, drop the
    "+", and hard-cap the width so an upstream format change can never
    take the run down again.
    """
    value = (raw or "").strip().lstrip("+")
    for sep in (" and ", ",", "/"):
        if sep in value:
            value = value.split(sep, 1)[0]
    return value.strip()[:10]


def _flag_from_iso2(code: str) -> str:
    """Compose the Unicode flag from an ISO-2 code: each letter becomes its
    regional-indicator symbol (U+1F1E6 + offset from 'A')."""
    code = (code or "").strip().upper()
    if len(code) != 2 or not code.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(ch) - ord("A")) for ch in code)


def _parse_country_info(raw: str, codes: set) -> list[dict]:
    """
    countryInfo.txt columns (tab-separated, '#'-prefixed lines are comments):
    ISO, ISO3, ISO-Numeric, fips, Country, Capital, Area, Population,
    Continent, tld, CurrencyCode, CurrencyName, Phone, PostalCodeFormat,
    PostalCodeRegex, Languages, geonameid, neighbours, EquivalentFipsCode
    """
    out = []
    for line in raw.splitlines():
        if not line or line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) < 13:
            continue
        iso2 = cols[0].strip()
        if codes and iso2.upper() not in codes:
            continue
        out.append({
            "iso2": iso2,
            "name": cols[4].strip(),
            "currency": cols[10].strip(),
            "currency_name": cols[11].strip(),
            "phone": _normalize_phone(cols[12]),
            "flag": _flag_from_iso2(iso2),
        })
    return out


def _parse_admin1_codes(raw: str, codes: set) -> dict[str, list[dict]]:
    """
    admin1CodesASCII.txt: no header, tab-separated
    code (e.g. "US.CA")  name  asciiname  geonameid
    Returns {iso2: [{code, name}, ...]}
    """
    by_country: dict[str, list[dict]] = {}
    for line in raw.splitlines():
        if not line:
            continue
        cols = line.split("\t")
        if len(cols) < 2:
            continue
        full_code = cols[0].strip()
        if "." not in full_code:
            continue
        iso2, admin1_code = full_code.split(".", 1)
        if codes and iso2.upper() not in codes:
            continue
        name = (cols[2].strip() or cols[1].strip())  # prefer asciiname, fallback to name
        by_country.setdefault(iso2, []).append({"code": admin1_code, "name": name})
    return by_country


def _parse_cities(lines: list[str], codes: set) -> list[dict]:
    """
    citiesXXXX.txt columns (tab-separated, no header, 19 fields):
    geonameid, name, asciiname, alternatenames, latitude, longitude,
    feature class, feature code, country code, cc2, admin1 code,
    admin2 code, admin3 code, admin4 code, population, elevation, dem,
    timezone, modification date
    """
    out = []
    for line in lines:
        if not line:
            continue
        cols = line.split("\t")
        if len(cols) < 11:
            continue
        iso2 = cols[8].strip()
        if codes and iso2.upper() not in codes:
            continue
        out.append({
            "name": (cols[2].strip() or cols[1].strip()),
            "iso2": iso2,
            "admin1_code": cols[10].strip(),
        })
    return out


def _upsert_country(conn, name: str, iso2: str, phone: str, currency: str, flag: str = "") -> int | None:
    if not name or not iso2:
        return None
    # Check first purely so the "added" tally is honest: with ON DUPLICATE
    # KEY UPDATE the driver reports matched (not changed) rows, so an
    # unchanged re-run still yields rowcount 1 and would inflate the count
    # with countries it did not actually add.
    existing = conn.execute(
        text("SELECT id FROM countries WHERE country_code=:c"), {"c": iso2}
    ).fetchone()
    # Single atomic statement - no SELECT+UPDATE race, no lock contention
    conn.execute(
        text(
            "INSERT INTO countries (country_name, country_code, phone_code, currency_code, flag_emoji, status) "
            "VALUES (:n, :c, :p, :cu, :fl, 'active') "
            "ON DUPLICATE KEY UPDATE country_name=VALUES(country_name), "
            "phone_code=VALUES(phone_code), currency_code=VALUES(currency_code), "
            "flag_emoji=VALUES(flag_emoji)"
        ),
        {"n": name, "c": iso2, "p": phone, "cu": currency, "fl": flag},
    )
    if existing:
        return existing[0]
    with _lock:
        _job["countries_added"] += 1
    row = conn.execute(text("SELECT id FROM countries WHERE country_code=:c"), {"c": iso2}).fetchone()
    return row[0] if row else None


# Symbols for the currencies GeoNames names but does not carry symbols for.
# Anything absent falls back to its own ISO code, which is a valid (if
# plain) way to render a price. Existing curated rows are never overwritten.
_CURRENCY_SYMBOLS = {
    "AED": "د.إ", "ARS": "$", "AUD": "A$", "BDT": "৳", "BGN": "лв", "BHD": ".د.ب",
    "BRL": "R$", "CAD": "C$", "CHF": "CHF", "CLP": "$", "CNY": "¥", "COP": "$",
    "CZK": "Kč", "DKK": "kr", "EGP": "E£", "EUR": "€", "FJD": "FJ$", "GBP": "£",
    "HKD": "HK$", "HUF": "Ft", "IDR": "Rp", "ILS": "₪", "INR": "₹", "ISK": "kr",
    "JPY": "¥", "KES": "KSh", "KRW": "₩", "KWD": "د.ك", "LKR": "Rs", "MAD": "د.م.",
    "MVR": "Rf", "MXN": "$", "MYR": "RM", "NGN": "₦", "NOK": "kr", "NPR": "Rs",
    "NZD": "NZ$", "OMR": "ر.ع.", "PEN": "S/", "PHP": "₱", "PKR": "Rs", "PLN": "zł",
    "QAR": "﷼", "RON": "lei", "RUB": "₽", "SAR": "﷼", "SEK": "kr", "SGD": "S$",
    "THB": "฿", "TRY": "₺", "TWD": "NT$", "TZS": "TSh", "UAH": "₴", "USD": "$",
    "VND": "₫", "ZAR": "R",
}


def _seed_currencies(conn, country_rows: list[dict]) -> int:
    """Upsert the distinct currencies referenced by the seeded countries.

    Only inserts currencies that aren't already present - the existing rows
    were curated by hand with proper symbols, so their name/symbol is left
    untouched.
    """
    seen: dict[str, str] = {}
    for c in country_rows:
        code = (c.get("currency") or "").strip().upper()
        if code and code not in seen:
            seen[code] = (c.get("currency_name") or "").strip() or code

    existing = {
        row[0].upper()
        for row in conn.execute(text("SELECT code FROM currencies")).fetchall()
        if row[0]
    }

    added = 0
    for code, name in sorted(seen.items()):
        if code in existing:
            continue
        conn.execute(
            text(
                "INSERT INTO currencies (name, code, symbol, status) "
                "VALUES (:n, :c, :s, 'active')"
            ),
            {"n": name, "c": code, "s": _CURRENCY_SYMBOLS.get(code, code)},
        )
        added += 1
    return added


def _upsert_state(conn, country_id: int, name: str, code: str) -> int | None:
    """Insert a state unless it already exists, returning its id either way.

    states has UNIQUE(country_id, state_name) (migration 0106), so INSERT
    IGNORE is atomic and cannot duplicate even under a concurrent run.
    Existing rows are deliberately left as-is rather than UPDATEd, to avoid
    write-lock contention across a ~3.9k-row pass.
    """
    if not name:
        return None
    result = conn.execute(
        text("INSERT IGNORE INTO states (country_id, state_name, state_code, status) VALUES (:cid, :n, :sc, 'active')"),
        {"cid": country_id, "n": name, "sc": code},
    )
    if result.rowcount:
        with _lock:
            _job["states_added"] += 1
    row = conn.execute(
        text("SELECT id FROM states WHERE country_id=:cid AND state_name=:n"),
        {"cid": country_id, "n": name},
    ).fetchone()
    return row[0] if row else None


def _upsert_city(conn, country_id: int, state_id: int | None, name: str) -> None:
    """Insert a city unless an identical one already exists.

    cities has UNIQUE(country_id, state_id, city_name) (migration 0106), so
    INSERT IGNORE makes the common path a single atomic statement that can
    never duplicate. MySQL still treats NULLs as distinct in a unique index,
    so a city with no state (a city-state such as Singapore) has to keep the
    explicit IS NULL check - the index cannot enforce that case.
    """
    if not name:
        return
    if state_id is None:
        exists = conn.execute(
            text("SELECT 1 FROM cities WHERE country_id=:cid AND state_id IS NULL AND city_name=:n"),
            {"cid": country_id, "n": name},
        ).fetchone()
        if exists:
            return
    result = conn.execute(
        text("INSERT IGNORE INTO cities (country_id, state_id, city_name, status) VALUES (:cid, :sid, :n, 'active')"),
        {"cid": country_id, "sid": state_id, "n": name},
    )
    if result.rowcount:
        with _lock:
            _job["cities_added"] += 1


def _run_phased(country_codes: list[str]) -> None:
    """
    Three-pass import from GeoNames bulk dump files:
      Phase 1 - upsert all countries       (countryInfo.txt)
      Phase 2 - upsert all states/admin1s  (admin1CodesASCII.txt)
      Phase 3 - upsert all cities          (citiesNNNN.zip)
    Exposes _job["phase"] (1/2/3) so callers can render per-phase progress.
    """
    codes = {c.upper() for c in country_codes}

    with _lock:
        _job.update({
            "running": True, "done": False, "error": None,
            "phase": 0, "phase_name": "Downloading",
            "total": 0, "processed": 0, "current": "Downloading country list from GeoNames...",
            "countries_added": 0, "states_added": 0, "cities_added": 0,
        })

    try:
        country_rows = _parse_country_info(_fetch_text(COUNTRY_INFO_URL), codes)

        with _lock:
            _job["current"] = "Downloading state/province list from GeoNames..."
        admin1_by_country = _parse_admin1_codes(_fetch_text(ADMIN1_CODES_URL), codes)

        with engine.connect() as conn:

            # phase 1: countries
            with _lock:
                _job.update({
                    "phase": 1, "phase_name": "Countries",
                    "total": len(country_rows), "processed": 0, "current": "Starting...",
                })

            country_map: dict[str, int] = {}  # iso2 -> db id
            for i, c in enumerate(country_rows, 1):
                with _lock:
                    _job["current"] = f"{c['name']} ({c['iso2']})"
                    _job["processed"] = i
                cid = _upsert_country(conn, c["name"], c["iso2"], c["phone"], c["currency"], c.get("flag", ""))
                if cid:
                    country_map[c["iso2"]] = cid
            _seed_currencies(conn, country_rows)
            conn.commit()

            # phase 2: states
            states_flat = [
                (iso2, country_map[iso2], s)
                for iso2, states in admin1_by_country.items()
                if iso2 in country_map
                for s in states
            ]
            with _lock:
                _job.update({
                    "phase": 2, "phase_name": "States",
                    "total": len(states_flat), "processed": 0, "current": "Starting...",
                })

            # state_map: (iso2, admin1_code) -> db id
            state_map: dict[tuple, int] = {}
            for i, (iso2, country_id, s) in enumerate(states_flat, 1):
                with _lock:
                    _job["current"] = f"{s['name']} ({iso2})"
                    _job["processed"] = i
                sid = _upsert_state(conn, country_id, s["name"], s["code"])
                if sid:
                    state_map[(iso2, s["code"])] = sid
            conn.commit()

            # phase 3: cities (only downloaded/parsed if any state was seeded,
            # i.e. include_cities path always calls this - see trigger below)
            with _lock:
                _job.update({"phase": 3, "phase_name": "Downloading cities", "current": "Downloading city list from GeoNames..."})
            city_rows = _parse_cities(_fetch_cities_lines(CITIES_URL), codes)

            with _lock:
                _job.update({
                    "phase": 3, "phase_name": "Cities",
                    "total": len(city_rows), "processed": 0, "current": "Starting...",
                })

            for i, city in enumerate(city_rows, 1):
                with _lock:
                    _job["current"] = city["name"]
                    _job["processed"] = i
                country_id = country_map.get(city["iso2"])
                if country_id:
                    # A city-state (Singapore) or a territory with no admin1
                    # division reports admin1 code "00"/unknown and has no
                    # matching state row -- seed it against the country with
                    # a NULL state rather than dropping it entirely.
                    state_id = state_map.get((city["iso2"], city["admin1_code"]))
                    _upsert_city(conn, country_id, state_id, city["name"])
                if i % 5000 == 0:
                    conn.commit()
            conn.commit()

        with _lock:
            _job.update({"running": False, "done": True, "current": "Completed"})

    except Exception as e:
        logger.exception("Geo phased seed failed: %s", e)
        with _lock:
            _job.update({"running": False, "done": True, "error": str(e), "current": "Failed"})


def _run_countries_and_states_only(country_codes: list[str]) -> None:
    """Same as _run_phased but skips downloading/parsing the (much larger)
    cities file entirely - used when include_cities=False."""
    codes = {c.upper() for c in country_codes}

    with _lock:
        _job.update({
            "running": True, "done": False, "error": None,
            "phase": 0, "phase_name": "Downloading",
            "total": 0, "processed": 0, "current": "Downloading country list from GeoNames...",
            "countries_added": 0, "states_added": 0, "cities_added": 0,
        })

    try:
        country_rows = _parse_country_info(_fetch_text(COUNTRY_INFO_URL), codes)

        with _lock:
            _job["current"] = "Downloading state/province list from GeoNames..."
        admin1_by_country = _parse_admin1_codes(_fetch_text(ADMIN1_CODES_URL), codes)

        with engine.connect() as conn:
            with _lock:
                _job.update({
                    "phase": 1, "phase_name": "Countries",
                    "total": len(country_rows), "processed": 0, "current": "Starting...",
                })

            country_map: dict[str, int] = {}
            for i, c in enumerate(country_rows, 1):
                with _lock:
                    _job["current"] = f"{c['name']} ({c['iso2']})"
                    _job["processed"] = i
                cid = _upsert_country(conn, c["name"], c["iso2"], c["phone"], c["currency"], c.get("flag", ""))
                if cid:
                    country_map[c["iso2"]] = cid
            _seed_currencies(conn, country_rows)
            conn.commit()

            states_flat = [
                (iso2, country_map[iso2], s)
                for iso2, states in admin1_by_country.items()
                if iso2 in country_map
                for s in states
            ]
            with _lock:
                _job.update({
                    "phase": 2, "phase_name": "States",
                    "total": len(states_flat), "processed": 0, "current": "Starting...",
                })

            for i, (iso2, country_id, s) in enumerate(states_flat, 1):
                with _lock:
                    _job["current"] = f"{s['name']} ({iso2})"
                    _job["processed"] = i
                _upsert_state(conn, country_id, s["name"], s["code"])
            conn.commit()

        with _lock:
            _job.update({"running": False, "done": True, "current": "Completed"})

    except Exception as e:
        logger.exception("Geo seed (countries+states) failed: %s", e)
        with _lock:
            _job.update({"running": False, "done": True, "error": str(e), "current": "Failed"})


@router.post("")
def trigger_geo_seed(
    background_tasks: BackgroundTasks,
    countries: Optional[List[str]] = Query(
        default=None,
        description="ISO2 codes to import. Omit for all ~250 countries.",
    ),
    include_cities: bool = Query(
        default=False,
        description="Also import cities (population >= 5000) for each state.",
    ),
    current_user: User = Depends(require_any_permission("settings.create")),
):
    """
    Trigger geo data import in the background, sourced from GeoNames
    (geonames.org) bulk dump files. Idempotent - safe to re-run.
    """
    with _lock:
        if _job["running"]:
            return {
                "status": "already_running",
                "message": "A geo import is already in progress.",
                "job": dict(_job),
            }

    target = _run_phased if include_cities else _run_countries_and_states_only
    background_tasks.add_task(target, countries or [])
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
