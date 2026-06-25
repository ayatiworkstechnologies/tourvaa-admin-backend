"""
Seed Countries / States / Cities from the GitHub geo dataset.

Primary source : github.com/dr5hn/countries-states-cities-database (one JSON, no rate limit)
Fallback source: countrystatecity.in API  (key from COUNTRY_STATE_CITY_API_KEY in .env)

Three sequential phases in a single trigger:
  Phase 1 — Countries   (upsert all country records)
  Phase 2 — States      (upsert all state/province records)
  Phase 3 — Cities      (upsert all city records)

Default countries (Tourvaa launch markets):
  US  United States    CA  Canada          IN  India
  NZ  New Zealand      AE  UAE             QA  Qatar
  LK  Sri Lanka        GB  United Kingdom  AU  Australia
  SG  Singapore

Run from the backend/ directory:

    # Default 10 countries → states → cities
    python -m scripts.seed_geo

    # Override with specific ISO-2 codes
    python -m scripts.seed_geo --countries IN AE US GB

    # All 250 countries (full dataset)
    python -m scripts.seed_geo --all
"""

import argparse
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.modules.cms.geo_seed_router import _job, _lock, _run_phased  # noqa: E402

LINE  = "─" * 64
THIN  = "·" * 44

# Tourvaa launch-market countries seeded by default
DEFAULT_COUNTRIES = ["US", "CA", "IN", "NZ", "AE", "QA", "LK", "GB", "AU", "SG"]

PHASE_LABELS = {1: "Countries", 2: "States", 3: "Cities"}


def _bar(done: int, total: int, width: int = 26) -> str:
    pct = done / max(total, 1)
    filled = int(pct * width)
    return "█" * filled + "░" * (width - filled)


def _pct(done: int, total: int) -> int:
    return int(done / max(total, 1) * 100)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed geo data (countries → states → cities) into Tourvaa DB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--countries",
        nargs="*",
        default=None,
        metavar="ISO2",
        help="Override the default 10 countries with specific ISO-2 codes.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Import all 250 countries instead of the default 10.",
    )
    args = parser.parse_args()

    if args.all:
        country_list: list[str] = []
        scope = "ALL 250 countries"
    elif args.countries is not None:
        country_list = [c.upper() for c in args.countries]
        scope = ", ".join(country_list)
    else:
        country_list = DEFAULT_COUNTRIES
        scope = ", ".join(DEFAULT_COUNTRIES) + "  (default)"

    print()
    print(LINE)
    print("  Tourvaa — Geo Data Seed  (Countries → States → Cities)")
    print(LINE)
    print(f"  Scope  : {scope}")
    print(f"  Source : GitHub (dr5hn/countries-states-cities-database)")
    print(LINE)

    thread = threading.Thread(
        target=_run_phased,
        args=(country_list,),
        daemon=True,
    )
    thread.start()

    displayed_phase = 0   # which phase header we've already printed
    phase_done_counts: dict[int, tuple[int, int, int]] = {}  # phase → (added, total, pct)

    while thread.is_alive():
        with _lock:
            j = dict(_job)

        phase     = j.get("phase", 0)
        p_name    = PHASE_LABELS.get(phase, "")
        done      = j["processed"]
        total     = j["total"]
        current   = (j["current"] or "")[:36]

        # Print phase header the first time we see a new phase number
        if phase > displayed_phase and phase in PHASE_LABELS:
            if displayed_phase > 0:
                # Close out the previous phase's progress line
                prev_counts = phase_done_counts.get(displayed_phase, (0, 0, 0))
                print(f"\r    [{_bar(prev_counts[1], prev_counts[1])}] 100%  {'done':<36}", flush=True)

            print(f"\n  Phase {phase}/3 — {p_name}")
            print(f"  {THIN}")
            displayed_phase = phase

        if phase > 0:
            bar  = _bar(done, total)
            pct  = _pct(done, total)
            print(f"\r    [{bar}] {pct:3d}%  {current:<36}", end="", flush=True)
            phase_done_counts[phase] = (phase_done_counts.get(phase, (0,0,0))[0], done, pct)

        time.sleep(0.35)

    thread.join()
    print()  # newline after last progress line

    with _lock:
        j = dict(_job)

    print()
    print(LINE)

    if j.get("error"):
        print(f"  FAILED: {j['error']}")
        print(LINE)
        sys.exit(1)

    print("  All phases complete.")
    print(f"  {THIN}")
    print(f"  Phase 1 — Countries : {j['countries_added']:>6} added")
    print(f"  Phase 2 — States    : {j['states_added']:>6} added")
    print(f"  Phase 3 — Cities    : {j['cities_added']:>6} added")
    print(LINE)
    print()


if __name__ == "__main__":
    main()
