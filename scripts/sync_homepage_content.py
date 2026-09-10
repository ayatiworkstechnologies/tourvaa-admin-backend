#!/usr/bin/env python
"""Copy homepage CMS content from one database to another - e.g. push what
you've built in the local admin panel to the live/production database.

Local dev and production are separate MySQL databases with no sync between
them (see app/config's DATABASE_URL vs. whatever the production deployment
sets), so content entered locally never appears live on its own. This
script wipes the listed homepage tables on the TARGET database and
re-inserts the SOURCE database's rows in their place.

DRY-RUN BY DEFAULT. Nothing is written unless --apply is passed, and
--apply still requires typing "yes" to confirm (or pass --yes to skip that
prompt for non-interactive use).

Usage (run from the backend root, same as the other scripts/ entries):
    # Preview what would change (no --target-url given -> error, on purpose)
    python -m scripts.sync_homepage_content --target-url mysql+pymysql://user:pass@host/db

    # Actually apply it
    python -m scripts.sync_homepage_content --target-url mysql+pymysql://user:pass@host/db --apply

Tables copied (homepage-rendered CMS content only - see
src/app/(public)/page.tsx on the frontend for what actually reads these):
    cms_homepage_banners, cms_popular_destinations, cms_popular_tours,
    cms_tours_on_deals, cms_handpicked_tours, cms_favourite_countries,
    cms_customer_reviews, cms_help_centre, and the four homepage keys in
    cms_homepage_content_blocks (hero_extras, about_section, blog_teaser,
    airport_transfer). Footer sections/links and CMS pages are a separate
    concern and are not touched here.

Two families of tables carry foreign keys that will NOT line up across two
independently-created databases, so they're remapped via natural keys
instead of trusting the raw ids:
    - PopularDestination.country_id/city_id, FavouriteCountryEntry.country_id
      -> remapped via Country.country_code (and city_name for city).
    - PopularTour/TourOnDeal/HandpickedTour.tour_id
      -> remapped via Tour.slug. If the pinned tour doesn't exist on the
         target (different slug, or not created there), that row is
         skipped with a clear warning naming the tour - never guessed.
"""
import argparse
import sys

import app.main  # noqa: F401  (imports every router so all SQLAlchemy models get registered)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models.cms import City, Country, Tour
from app.models.website_cms import (
    CustomerReview, FavouriteCountryEntry, HandpickedTour, HelpCentreArticle,
    HomepageBanner, HomepageContentBlock, PopularDestination, PopularTour,
    TourOnDeal,
)

HOMEPAGE_CONTENT_BLOCK_KEYS = {"hero_extras", "about_section", "blog_teaser", "airport_transfer"}

PLAIN_TABLES = [
    (HomepageBanner, ["title", "subtitle", "image", "video", "cta_text", "cta_url", "sort_order", "is_active"]),
    (CustomerReview, ["reviewer_name", "reviewer_image", "rating", "review_text", "tour_name", "country", "sort_order", "is_active"]),
    (HelpCentreArticle, ["category", "question", "answer", "sort_order", "is_active"]),
]

TOUR_REF_TABLES = [
    (PopularTour, []),
    (HandpickedTour, []),
    (TourOnDeal, ["deal_label", "discount_percentage", "valid_until"]),
]


def make_session(url: str):
    engine = create_engine(url, pool_pre_ping=True)
    return sessionmaker(bind=engine)()


def normalize_url(url: str) -> str:
    return url.strip().rstrip("/")


def plan_plain_table(source, model, columns):
    rows = [{col: getattr(r, col) for col in columns} for r in source.query(model).all()]
    return rows, []


def plan_geo_tables(source, target):
    """PopularDestination + FavouriteCountryEntry - both reference
    country_id (nullable) and, for PopularDestination only, city_id."""
    source_country_by_id = {c.id: c for c in source.query(Country).all()}
    target_country_by_code = {c.country_code: c.id for c in target.query(Country).all()}
    source_city_by_id = {c.id: c for c in source.query(City).all()}
    target_city_by_key = {(c.country_id, c.city_name.strip().lower()): c.id for c in target.query(City).all()}

    def remap_country(source_country_id):
        if source_country_id is None:
            return None, None
        src = source_country_by_id.get(source_country_id)
        if not src:
            return None, f"source country id {source_country_id} not found on source (data inconsistency)"
        target_id = target_country_by_code.get(src.country_code)
        if not target_id:
            return None, f"country '{src.country_name}' ({src.country_code}) not found on target"
        return target_id, None

    def remap_city(source_city_id, remapped_country_id):
        if source_city_id is None:
            return None, None
        src = source_city_by_id.get(source_city_id)
        if not src:
            return None, f"source city id {source_city_id} not found on source (data inconsistency)"
        if remapped_country_id is None:
            return None, f"city '{src.city_name}' dropped (its country wasn't remapped)"
        target_id = target_city_by_key.get((remapped_country_id, src.city_name.strip().lower()))
        if not target_id:
            return None, f"city '{src.city_name}' not found on target under its remapped country"
        return target_id, None

    plans = {}
    warnings = []

    dest_rows, dest_skips = [], []
    for r in source.query(PopularDestination).all():
        country_id, err = remap_country(r.country_id)
        if r.country_id is not None and err:
            dest_skips.append(f"PopularDestination '{r.title}': {err}")
            continue
        city_id, city_err = remap_city(r.city_id, country_id)
        if city_err:
            warnings.append(f"PopularDestination '{r.title}': {city_err}")
        dest_rows.append({
            "country_id": country_id, "city_id": city_id, "title": r.title, "image": r.image,
            "description": r.description, "sort_order": r.sort_order, "is_active": r.is_active,
        })
    plans[PopularDestination] = (dest_rows, dest_skips)

    fav_rows, fav_skips = [], []
    for r in source.query(FavouriteCountryEntry).all():
        country_id, err = remap_country(r.country_id)
        if r.country_id is not None and err:
            fav_skips.append(f"FavouriteCountryEntry '{r.title}': {err}")
            continue
        fav_rows.append({
            "country_id": country_id, "title": r.title, "snippet": r.snippet, "image": r.image,
            "href": r.href, "sort_order": r.sort_order, "is_active": r.is_active,
        })
    plans[FavouriteCountryEntry] = (fav_rows, fav_skips)

    return plans, warnings


def plan_tour_ref_tables(source, target):
    source_tour_by_id = {t.id: t for t in source.query(Tour).all()}
    target_tour_by_slug = {t.slug: t.id for t in target.query(Tour).all()}

    def remap_tour(source_tour_id):
        src = source_tour_by_id.get(source_tour_id)
        if not src:
            return None, f"source tour id {source_tour_id} not found on source (data inconsistency)"
        target_id = target_tour_by_slug.get(src.slug)
        if not target_id:
            return None, f"tour '{src.title}' (slug={src.slug}) not found on target - create/publish it there first"
        return target_id, None

    plans = {}
    for model, extra_columns in TOUR_REF_TABLES:
        rows, skips = [], []
        for r in source.query(model).all():
            tour_id, err = remap_tour(r.tour_id)
            if err:
                skips.append(f"{model.__name__} #{r.id}: {err}")
                continue
            row = {"tour_id": tour_id, "sort_order": r.sort_order, "is_active": r.is_active}
            for col in extra_columns:
                row[col] = getattr(r, col)
            rows.append(row)
        plans[model] = (rows, skips)
    return plans


def plan_content_blocks(source):
    rows = [
        {"key": r.key, "data": r.data}
        for r in source.query(HomepageContentBlock).filter(HomepageContentBlock.key.in_(HOMEPAGE_CONTENT_BLOCK_KEYS)).all()
    ]
    return rows, []


def apply_table(target, model, rows):
    target.query(model).delete()
    for row in rows:
        target.add(model(**row))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source-url", default=settings.DATABASE_URL, help="Source DB (default: local .env DATABASE_URL)")
    parser.add_argument("--target-url", required=True, help="Target DB to write to (required, never defaulted)")
    parser.add_argument("--apply", action="store_true", help="Actually write changes (default: dry-run only)")
    parser.add_argument("--yes", action="store_true", help="Skip the interactive confirmation prompt when --apply is used")
    args = parser.parse_args()

    if normalize_url(args.source_url) == normalize_url(args.target_url):
        print("ERROR: source and target resolve to the same database - refusing to run.", file=sys.stderr)
        sys.exit(1)

    source = make_session(args.source_url)
    target = make_session(args.target_url)

    try:
        table_plans: list[tuple[str, object, list[dict], list[str]]] = []

        for model, columns in PLAIN_TABLES:
            rows, skips = plan_plain_table(source, model, columns)
            table_plans.append((model.__tablename__, model, rows, skips))

        geo_plans, geo_warnings = plan_geo_tables(source, target)
        for model, (rows, skips) in geo_plans.items():
            table_plans.append((model.__tablename__, model, rows, skips))

        tour_plans = plan_tour_ref_tables(source, target)
        for model, (rows, skips) in tour_plans.items():
            table_plans.append((model.__tablename__, model, rows, skips))

        block_rows, block_skips = plan_content_blocks(source)
        table_plans.append(("cms_homepage_content_blocks (homepage keys)", HomepageContentBlock, block_rows, block_skips))

        print(f"Source: {args.source_url}")
        print(f"Target: {args.target_url}")
        print()
        print("=" * 70)
        for table_name, _model, rows, skips in table_plans:
            print(f"{table_name}: {len(rows)} row(s) to copy, {len(skips)} skipped")
            for skip in skips:
                print(f"    SKIP: {skip}")
        for warning in geo_warnings:
            print(f"  WARNING: {warning}")
        print("=" * 70)

        if not args.apply:
            print("\nDry run only - nothing written. Re-run with --apply to write these changes.")
            return

        print("\nThis will DELETE and REPLACE the following tables on the TARGET database:")
        for table_name, _model, _rows, _skips in table_plans:
            print(f"  - {table_name}")

        if not args.yes:
            confirm = input("\nType 'yes' to continue: ").strip().lower()
            if confirm != "yes":
                print("Aborted - target was not modified.")
                return

        for _table_name, model, rows, _skips in table_plans:
            if model is HomepageContentBlock:
                target.query(HomepageContentBlock).filter(HomepageContentBlock.key.in_(HOMEPAGE_CONTENT_BLOCK_KEYS)).delete(synchronize_session=False)
                for row in rows:
                    target.add(HomepageContentBlock(**row))
            else:
                apply_table(target, model, rows)

        target.commit()
        print("\nDone - target database updated.")
    except Exception:
        target.rollback()
        raise
    finally:
        source.close()
        target.close()


if __name__ == "__main__":
    main()
