"""
Creates one fully-populated, published demo tour end to end (same depth as
scripts/seed_demo_tour.py) for the "3-Day Milford Sound Fiordland Discovery"
tour referenced by scripts/generate_tour_import_excel.py - the Excel import
only creates the basic fields, this fills in every other wizard section too.

Run from the backend root: python -m scripts.seed_milford_sound_tour
"""
import app.main  # noqa: F401  (imports every router so all SQLAlchemy models get registered)

from datetime import datetime, timedelta, timezone

from app.database import SessionLocal
from app.models.cms import City, Country, Tour, TourCategory
from app.models.roles import Role
from app.models.suppliers import Supplier
from app.models.users import User

from app.schemas.cms import StatusUpdate, TourPayload
from app.schemas.tours import (
    AccommodationExtraPayload,
    CalendarPayload,
    DiscountPayload,
    GalleryImagePayload,
    HighlightPayload,
    InclusionPayload,
    ItineraryPayload,
    OptionalActivityPayload,
    PricingPayload,
    TourOverviewPayload,
)

from app.services.cms import save_tour, update_status, _tour
from app.services import tours as tour_services

IMG = "https://images.unsplash.com/{path}?auto=format&fit=crop&w=1600&q=80"

HERO_IMAGES = [
    IMG.format(path="photo-1578662996442-48f60103fc96"),  # Milford Sound fiord
    IMG.format(path="photo-1601604860710-b6bcda123415"),  # Fiordland waterfall
]
GALLERY_IMAGES = [
    IMG.format(path="photo-1502786129293-79981df4e689"),
    IMG.format(path="photo-1500534623283-312aade485b7"),
    IMG.format(path="photo-1518623489648-a173ef7824f3"),
    IMG.format(path="photo-1470071459604-3b5ec3a7fe05"),
]
DAY_IMAGES = [
    IMG.format(path="photo-1469854523086-cc02fe5d8800"),
    IMG.format(path="photo-1493246507139-91e8fad9978e"),
    IMG.format(path="photo-1506197603052-3cc9c3a201bd"),
]
HIGHLIGHT_IMAGES = [
    IMG.format(path="photo-1578662996442-48f60103fc96"),
    IMG.format(path="photo-1544551763-46a013bb70d5"),
    IMG.format(path="photo-1445307806294-bff7f67ff225"),
]


def main():
    db = SessionLocal()
    try:
        admin_user = (
            db.query(User)
            .join(Role, User.role_id == Role.id)
            .filter(Role.slug.in_(["admin", "super-admin"]))
            .order_by(User.id.asc())
            .first()
        )
        if not admin_user:
            raise SystemExit("No admin user found - seed the app first (app.seed) before running this script.")

        supplier = db.query(Supplier).filter(Supplier.approval_status == "APPROVED").order_by(Supplier.id.asc()).first()
        if not supplier:
            raise SystemExit("No approved supplier found - approve at least one supplier before running this script.")

        country = db.query(Country).filter(Country.country_name == "New Zealand").first()
        city = db.query(City).filter(City.country_id == country.id, City.city_name.ilike("%queenstown%")).first()
        category = db.query(TourCategory).filter(TourCategory.category_name == "Adventure Tours").first()

        currency = "NZD"

        # 1. Base tour -----------------------------------------------------
        tour_payload = TourPayload(
            supplier_id=supplier.id,
            title="3-Day Milford Sound Fiordland Discovery",
            subtitle="Queenstown to Milford Sound and back in style",
            country_id=country.id,
            city_id=city.id if city else None,
            category_id=category.id if category else None,
            start_location="Queenstown",
            finish_location="Queenstown",
            number_of_days=3,
            number_of_nights=2,
            max_group_size=12,
            min_booking_size=1,
            tour_language="English",
            suitable_age_range="10+",
            tour_visibility="public",
            featured=True,
            currency=currency,
            short_description="A compact 3-day escape from Queenstown into Fiordland National Park, cruising Milford Sound and exploring the Southern Alps along the way.",
            long_description=(
                "Escape Queenstown for three unforgettable days in Fiordland National Park, a UNESCO World "
                "Heritage site. Cruise beneath the towering cliffs and cascading waterfalls of Milford Sound, "
                "spot fur seals, penguins, and dolphins in their natural habitat, and wind through some of the "
                "most dramatic alpine scenery on Earth via the Milford Road. Comfortable lodges and small-group "
                "coach travel make this the easiest way to see New Zealand's most iconic fiord."
            ),
            pricing_type="per_person",
            booking_deposit=120,
            balance_payment_deadline_days=14,
            requires_supplier_confirmation=True,
            seo_title="3-Day Milford Sound Fiordland Discovery Tour | Queenstown",
            seo_description="Book a 3-day guided tour from Queenstown to Milford Sound, cruising Fiordland National Park with lodge accommodation included.",
            seo_keywords="Milford Sound tour, Queenstown tour, Fiordland National Park",
            focus_keyword="Milford Sound tour from Queenstown",
            image_alt_text="Milford Sound fiord cliffs and waterfalls under a cloudy sky",
            banner_image=HERO_IMAGES[0],
            tour_video_url="https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4",
        )
        created = save_tour(db, tour_payload, admin_user)
        tour_id = created["id"]
        print(f"Created tour #{tour_id}: {created['title']}")

        # 2. Overview --------------------------------------------------------
        tour_services.save_overview(db, tour_id, TourOverviewPayload(
            duration_text="3 Days / 2 Nights",
            start_location="Queenstown",
            end_location="Queenstown",
            group_size="Up to 12 travellers",
            tour_type="Small-group coach tour",
            physical_rating="easy",
            why_choose_this_tour="See Milford Sound and the Southern Alps without planning any logistics yourself - everything is arranged.",
            ideal_for="Couples, families, and short-stay visitors wanting Fiordland's highlights without a long commitment.",
            best_season="November to March (New Zealand summer)",
            tour_pace="Easy",
            transportation_summary="Private coach with driver-guide, plus the Milford Sound cruise vessel",
            accommodation_summary="4-star lodges (or similar), twin/double share",
            meal_summary="Daily breakfast, 1 dinner, lunch included on the cruise day",
        ), admin_user)
        print("  overview saved")

        # 3. Itinerary -----------------------------------------------------
        itinerary_days = [
            dict(day_number=1, day_title="Queenstown to Te Anau", location_name="Te Anau",
                 short_description="Depart Queenstown and travel through rolling farmland to the lakeside town of Te Anau, gateway to Fiordland.",
                 activities="Lake Wakatipu lookout stop, Te Anau glowworm caves evening tour",
                 accommodation="Te Anau Lakefront Lodge", meals_included="Breakfast",
                 travel_distance="170 km", travel_duration="2 hours", transport_type="Private coach"),
            dict(day_number=2, day_title="Milford Sound Cruise Day", location_name="Milford Sound",
                 short_description="Drive the spectacular Milford Road through the Southern Alps, then cruise Milford Sound beneath its towering cliffs and waterfalls.",
                 activities="Milford Road scenic stops, Milford Sound cruise with lunch, wildlife spotting (seals, dolphins, penguins)",
                 accommodation="Te Anau Lakefront Lodge", meals_included="Breakfast, Lunch, Dinner",
                 important_notes="Cruise departure times may shift slightly with weather and tide conditions."),
            dict(day_number=3, day_title="Return to Queenstown", location_name="Queenstown",
                 short_description="A scenic return drive to Queenstown, with free time to explore the town before the tour concludes.",
                 activities="Free time on Queenstown's lakefront, optional gondola ride",
                 accommodation="Not included (tour concludes)", meals_included="Breakfast",
                 travel_distance="170 km", travel_duration="2 hours"),
        ]
        for index, day in enumerate(itinerary_days):
            tour_services.create_itinerary(db, tour_id, ItineraryPayload(image=DAY_IMAGES[index], **day), admin_user)
        print(f"  {len(itinerary_days)} itinerary days added")

        # 4. Highlights ------------------------------------------------------
        highlights = [
            ("Milford Sound Cruise", "Sail beneath 1,200-metre cliffs and cascading waterfalls on New Zealand's most iconic fiord."),
            ("Te Anau Glowworm Caves", "An evening boat tour through a limestone cave illuminated by thousands of glowworms."),
            ("The Milford Road", "One of the world's most scenic drives, winding through alpine valleys and the Homer Tunnel."),
        ]
        for index, (title, description) in enumerate(highlights):
            tour_services.create_highlight(db, tour_id, HighlightPayload(image=HIGHLIGHT_IMAGES[index], title=title, short_description=description, display_order=index), admin_user)
        print(f"  {len(highlights)} highlights added")

        # 5. Inclusions / exclusions -----------------------------------------
        inclusions = [
            "2 nights accommodation (4-star lodge)",
            "Daily breakfast, 1 dinner, and lunch on the cruise day",
            "Milford Sound cruise ticket",
            "Te Anau glowworm caves tour",
            "Professional English-speaking driver-guide throughout",
        ]
        for index, title in enumerate(inclusions):
            tour_services.create_inclusion(db, tour_id, InclusionPayload(title=title, display_order=index), admin_user)
        exclusions = [
            "Flights to/from Queenstown",
            "Travel insurance",
            "Optional Queenstown gondola ride",
            "Personal expenses and gratuities",
        ]
        for index, title in enumerate(exclusions):
            tour_services.create_exclusion(db, tour_id, InclusionPayload(title=title, display_order=index), admin_user)
        print(f"  {len(inclusions)} inclusions, {len(exclusions)} exclusions added")

        # 6. Gallery: banner (hero) + regular gallery images -------------------
        for index, url in enumerate(HERO_IMAGES):
            tour_services.create_gallery_image(db, tour_id, GalleryImagePayload(image_path=url, image_type="banner", image_title=f"Hero image {index + 1}", display_order=index), admin_user)
        for index, url in enumerate(GALLERY_IMAGES):
            tour_services.create_gallery_image(db, tour_id, GalleryImagePayload(image_path=url, image_type="gallery", image_title=f"Gallery image {index + 1}", display_order=index), admin_user)
        print(f"  {len(HERO_IMAGES)} banner + {len(GALLERY_IMAGES)} gallery images added")

        # 7. Pricing (commission floored at the supplier's agreed rate) --------
        supplier_commission = supplier.markup_value or 0.0
        tour_services.create_pricing(db, tour_id, PricingPayload(
            passenger_from=1, passenger_to=4, adult_price=650, child_price=420, currency=currency,
            markup_value=supplier_commission, admin_markup_type="percentage", admin_markup_value=15,
        ), admin_user)
        tour_services.create_pricing(db, tour_id, PricingPayload(
            passenger_from=5, passenger_to=12, adult_price=590, child_price=380, currency=currency,
            markup_value=supplier_commission, admin_markup_type="percentage", admin_markup_value=15,
        ), admin_user)
        print("  2 pricing slabs added")

        # 8. Optional activities & accommodation extras -------------------------
        activities = [
            ("Queenstown Gondola & Luge", "Ride the gondola for alpine views, then race down the luge track.", 55, "extra_activity"),
            ("Milford Sound Overnight Cruise Upgrade", "Swap the day cruise for an overnight stay aboard the boat.", 240, "other"),
        ]
        for name, description, price, category_slug in activities:
            tour_services.create_activity(db, tour_id, OptionalActivityPayload(activity_name=name, description=description, price_per_person=price, category=category_slug), admin_user)
        accommodations = [
            ("Lake View Room Upgrade", "Upgrade to a lake-facing room in Te Anau.", 45, "room_upgrade"),
        ]
        for name, description, price, category_slug in accommodations:
            tour_services.create_accommodation(db, tour_id, AccommodationExtraPayload(accommodation_name=name, description=description, extra_price=price, category=category_slug), admin_user)
        print(f"  {len(activities)} optional activities, {len(accommodations)} accommodation extras added")

        # 9. Calendar departures (one low-stock, to exercise "Seats Left") ------
        now = datetime.now(timezone.utc)
        departures = [
            (now + timedelta(days=14), 12),
            (now + timedelta(days=28), 3),
            (now + timedelta(days=42), 12),
        ]
        for date, seats in departures:
            tour_services.create_calendar_entry(db, tour_id, CalendarPayload(tour_date=date, available_seats=seats, status="available"), admin_user)
        print(f"  {len(departures)} calendar departures added")

        # 10. Discount (drives the "You Save" banner) ---------------------------
        tour_services.create_discount(db, tour_id, DiscountPayload(
            discount_name="Book Direct 8% Off",
            discount_code="MILFORD8",
            discount_type="percentage",
            discount_value=8,
            discount_scope="tour",
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=60),
        ), admin_user)
        print("  1 active discount added")

        # 11. Publish ---------------------------------------------------------
        update_status(db, Tour, _tour, tour_id, StatusUpdate(status="published"), admin_user, "tour")
        tour = db.query(Tour).filter(Tour.id == tour_id).first()
        print(f"\nPublished. slug={tour.slug!r} price_start_per_person={tour.price_start_per_person} {tour.currency}")
        print(f"Public URL:  /tours/{tour_id}/{tour.slug}")
        print(f"Admin edit:  /admin/tours/{tour_id}/edit")
        print(f"Supplier edit (supplier #{supplier.id}): /supplier/tours/{tour_id}/edit")

    finally:
        db.close()


if __name__ == "__main__":
    main()
