"""
Creates one fully-populated, published demo tour end to end - every wizard
section (basic details, location & category, overview & highlights,
itinerary, pricing, accommodation, activities & add-ons, inclusions &
policies, gallery & media/SEO, calendar, discounts) - so there's a real tour
to click through manually on both the supplier/admin portals and the public
site (hero carousel, gallery lightbox, Tour Highlights grid, itinerary
accordion, You Save banner, booking flow).

Run from the backend root: python -m scripts.seed_demo_tour
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
    ExtensionPayload,
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
    IMG.format(path="photo-1469521669194-babb45599def"),  # NZ mountains/lake
    IMG.format(path="photo-1507699622108-4be3abd695ad"),  # NZ coastline
]
GALLERY_IMAGES = [
    IMG.format(path="photo-1518837695005-2083093ee35b"),
    IMG.format(path="photo-1490750967868-88aa4486c946"),
    IMG.format(path="photo-1500534623283-312aade485b7"),
    IMG.format(path="photo-1500375592092-40eb2168fd21"),
    IMG.format(path="photo-1476514525535-07fb3b4ae5f1"),
    IMG.format(path="photo-1544551763-46a013bb70d5"),
]
DAY_IMAGES = [
    IMG.format(path="photo-1507525428034-b723cf961d3e"),
    IMG.format(path="photo-1493246507139-91e8fad9978e"),
    IMG.format(path="photo-1526772662000-3f88f10405ff"),
    IMG.format(path="photo-1445307806294-bff7f67ff225"),
    IMG.format(path="photo-1589802829985-817e51171b92"),
    IMG.format(path="photo-1512918728675-ed5a9ecdebfd"),
    IMG.format(path="photo-1469854523086-cc02fe5d8800"),
]
HIGHLIGHT_IMAGES = [
    IMG.format(path="photo-1447752875215-b2761acb3c5d"),
    IMG.format(path="photo-1528184039930-bd03972bd974"),
    IMG.format(path="photo-1500932334442-8761ee4810a7"),
    IMG.format(path="photo-1470770903676-69b98201ea1c"),
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
        if not country:
            country = db.query(Country).order_by(Country.id.asc()).first()
        city = db.query(City).filter(City.country_id == country.id, City.city_name.ilike("%auckland%")).first()
        if not city:
            city = db.query(City).filter(City.country_id == country.id).first()
        category = db.query(TourCategory).filter(TourCategory.category_name == "Adventure Tours").first()
        if not category:
            category = db.query(TourCategory).order_by(TourCategory.id.asc()).first()

        # An existing tour to attach as a paid extension, so the Extensions
        # tab has real data too. Any other published tour works.
        extension_target = db.query(Tour).filter(Tour.id != None).order_by(Tour.id.desc()).first()  # noqa: E711

        currency = "NZD"

        # 1. Base tour -----------------------------------------------------
        tour_payload = TourPayload(
            supplier_id=supplier.id,
            title="7-Day New Zealand Grand Adventure: Auckland to Queenstown",
            subtitle="Glaciers, geysers, and fjords - the North and South Islands in one unforgettable week",
            country_id=country.id,
            city_id=city.id if city else None,
            category_id=category.id if category else None,
            start_location="Auckland",
            finish_location="Queenstown",
            number_of_days=7,
            number_of_nights=6,
            max_group_size=16,
            min_booking_size=1,
            tour_language="English",
            suitable_age_range="8+",
            tour_visibility="public",
            featured=True,
            currency=currency,
            short_description="From Auckland's harbour to Queenstown's alpine peaks - geothermal wonders, glowworm caves, and the dramatic scenery of both islands in a single seamlessly planned week.",
            long_description=(
                "Experience the very best of New Zealand on this seven-day journey across the North and South "
                "Islands. Begin in Auckland and travel through the geothermal wonderland of Rotorua, the "
                "adventure capital of Taupo, and the windswept capital city of Wellington, before crossing to "
                "the South Island to explore Kaikoura's coastline and finish amid the Southern Alps in "
                "Queenstown. Every day blends guided sightseeing with free time to explore at your own pace, "
                "with comfortable coach transfers and hand-picked accommodation throughout."
            ),
            pricing_type="per_person",
            booking_deposit=250,
            balance_payment_deadline_days=21,
            requires_supplier_confirmation=True,
            seo_title="7-Day New Zealand Grand Adventure Tour | Auckland to Queenstown",
            seo_description="Book a 7-day guided New Zealand tour from Auckland to Queenstown, covering Rotorua, Taupo, Wellington, Kaikoura and the Southern Alps.",
            seo_keywords="New Zealand tour, Auckland to Queenstown, North Island South Island tour",
            focus_keyword="New Zealand grand adventure tour",
            image_alt_text="Snow-capped mountains reflected in a New Zealand lake",
            banner_image=HERO_IMAGES[0],
            tour_video_url="https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4",
        )
        created = save_tour(db, tour_payload, admin_user)
        tour_id = created["id"]
        print(f"Created tour #{tour_id}: {created['title']}")

        # 2. Overview --------------------------------------------------------
        tour_services.save_overview(db, tour_id, TourOverviewPayload(
            duration_text="7 Days / 6 Nights",
            start_location="Auckland",
            end_location="Queenstown",
            group_size="Up to 16 travellers",
            tour_type="Guided coach tour",
            physical_rating="moderate",
            why_choose_this_tour="A single, seamlessly planned trip covering both islands' unmissable highlights - no logistics to plan yourself.",
            ideal_for="First-time visitors to New Zealand, couples, and small groups of friends.",
            best_season="October to April (New Zealand spring through autumn)",
            tour_pace="Moderate",
            transportation_summary="Private air-conditioned coach with a professional driver-guide, plus one scenic inter-island flight",
            accommodation_summary="4-star hotels and lodges (or similar), twin/double share",
            meal_summary="Daily breakfast, 3 dinners, and a traditional Maori hangi feast",
        ), admin_user)
        print("  overview saved")

        # 3. Itinerary ---------------------------------------------------------
        itinerary_days = [
            dict(day_number=1, day_title="Welcome to Auckland", location_name="Auckland",
                 short_description="Arrive in Auckland and settle in before an evening harbour cruise.",
                 activities="Airport meet & greet, Auckland harbour sunset cruise, welcome dinner",
                 accommodation="Auckland City Hotel", meals_included="Dinner", start_time="14:00", end_time="20:00"),
            dict(day_number=2, day_title="Auckland to Coromandel Peninsula", location_name="Coromandel Peninsula",
                 short_description="Travel south along the coast to the Coromandel Peninsula, stopping at Cathedral Cove.",
                 activities="Cathedral Cove clifftop walk, Hot Water Beach, local craft market",
                 accommodation="Coromandel Lodge", meals_included="Breakfast",
                 travel_distance="185 km", travel_duration="2.5 hours", transport_type="Private coach"),
            dict(day_number=3, day_title="Coromandel to Rotorua", location_name="Rotorua",
                 short_description="Journey inland to Rotorua, New Zealand's geothermal and Maori cultural heartland.",
                 activities="Te Puia geothermal park, geyser viewing, traditional Maori hangi and cultural show",
                 accommodation="Rotorua Geyserland Hotel", meals_included="Breakfast, Dinner"),
            dict(day_number=4, day_title="Rotorua to Taupo", location_name="Taupo",
                 short_description="A short scenic drive to Lake Taupo, New Zealand's adventure capital.",
                 activities="Huka Falls, optional bungy jump, Lake Taupo cruise",
                 accommodation="Taupo Lakefront Lodge", meals_included="Breakfast",
                 travel_distance="80 km", travel_duration="1 hour"),
            dict(day_number=5, day_title="Taupo to Wellington", location_name="Wellington",
                 short_description="Travel south to the capital, Wellington, with its harbour and hillside views.",
                 activities="Te Papa Museum, cable car to Mount Victoria lookout",
                 accommodation="Wellington Harbour Hotel", meals_included="Breakfast",
                 travel_distance="335 km", travel_duration="4.5 hours"),
            dict(day_number=6, day_title="Wellington to Kaikoura", location_name="Kaikoura",
                 short_description="Cross to the South Island by ferry and continue along the coast to Kaikoura.",
                 activities="Interislander ferry crossing, whale-watching cruise, seal colony walk",
                 accommodation="Kaikoura Coastal Inn", meals_included="Breakfast, Dinner"),
            dict(day_number=7, day_title="Kaikoura to Queenstown", location_name="Queenstown",
                 short_description="Final scenic transfer through the Southern Alps to adventure-capital Queenstown, where the tour concludes.",
                 activities="Scenic flight over the Southern Alps, free time on Queenstown's lakefront",
                 accommodation="Not included (tour concludes)", meals_included="Breakfast",
                 important_notes="Onward travel and accommodation in Queenstown are not included."),
        ]
        for index, day in enumerate(itinerary_days):
            tour_services.create_itinerary(db, tour_id, ItineraryPayload(image=DAY_IMAGES[index], **day), admin_user)
        print(f"  {len(itinerary_days)} itinerary days added")

        # 4. Highlights ----------------------------------------------------
        highlights = [
            ("Cathedral Cove", "Walk down to one of New Zealand's most photographed coves, framed by a dramatic natural rock arch."),
            ("Rotorua Geothermal Park", "Watch geysers erupt and taste a traditional hangi feast cooked in the earth."),
            ("Whale Watching in Kaikoura", "Spot sperm whales and dusky dolphins on a guided cruise off the Kaikoura coast."),
            ("Southern Alps Scenic Flight", "Soar over glaciers and alpine lakes on the final approach into Queenstown."),
        ]
        for index, (title, description) in enumerate(highlights):
            tour_services.create_highlight(db, tour_id, HighlightPayload(image=HIGHLIGHT_IMAGES[index], title=title, short_description=description, display_order=index), admin_user)
        print(f"  {len(highlights)} highlights added")

        # 5. Inclusions / exclusions ----------------------------------------
        inclusions = [
            "6 nights accommodation (4-star hotels/lodges)",
            "Daily breakfast, 3 dinners, and 1 traditional hangi feast",
            "All coach transfers and the Wellington-Picton ferry crossing",
            "Professional English-speaking driver-guide throughout",
            "Entry fees for Te Puia, Cathedral Cove, and the whale-watching cruise",
        ]
        for index, title in enumerate(inclusions):
            tour_services.create_inclusion(db, tour_id, InclusionPayload(title=title, display_order=index), admin_user)
        exclusions = [
            "International and domestic flights to/from New Zealand",
            "Travel insurance",
            "Optional activities (bungy jump, scenic flight upgrades)",
            "Personal expenses and gratuities",
        ]
        for index, title in enumerate(exclusions):
            tour_services.create_exclusion(db, tour_id, InclusionPayload(title=title, display_order=index), admin_user)
        print(f"  {len(inclusions)} inclusions, {len(exclusions)} exclusions added")

        # 6. Gallery: 2 hero/banner images + 6 regular gallery images --------
        for index, url in enumerate(HERO_IMAGES):
            tour_services.create_gallery_image(db, tour_id, GalleryImagePayload(image_path=url, image_type="banner", image_title=f"Hero image {index + 1}", display_order=index), admin_user)
        for index, url in enumerate(GALLERY_IMAGES):
            tour_services.create_gallery_image(db, tour_id, GalleryImagePayload(image_path=url, image_type="gallery", image_title=f"Gallery image {index + 1}", display_order=index), admin_user)
        print(f"  {len(HERO_IMAGES)} banner + {len(GALLERY_IMAGES)} gallery images added")

        # 7. Pricing slabs -----------------------------------------------------
        # markup_value is this supplier's own commission for the slab - the
        # server floors it at Supplier.markup_value (their agreed rate), so
        # pass that rate straight through rather than hardcoding a guess.
        supplier_commission = supplier.markup_value or 0.0
        tour_services.create_pricing(db, tour_id, PricingPayload(
            passenger_from=1, passenger_to=4, adult_price=1450, child_price=980, currency=currency,
            markup_value=supplier_commission, admin_markup_type="percentage", admin_markup_value=15,
        ), admin_user)
        tour_services.create_pricing(db, tour_id, PricingPayload(
            passenger_from=5, passenger_to=16, adult_price=1290, child_price=870, currency=currency,
            markup_value=supplier_commission, admin_markup_type="percentage", admin_markup_value=15,
        ), admin_user)
        print("  2 pricing slabs added")

        # 8. Optional activities & accommodation extras -----------------------
        activities = [
            ("Queenstown Bungy Jump", "Take the leap at the original Kawarau Bridge Bungy.", 220, "extra_activity"),
            ("Wellington Cable Car Return", "Round-trip ride with panoramic harbour views.", 25, "extra_activity"),
            ("Private Photography Add-on", "A local photographer joins for the Cathedral Cove stop.", 95, "other"),
        ]
        for name, description, price, category_slug in activities:
            tour_services.create_activity(db, tour_id, OptionalActivityPayload(activity_name=name, description=description, price_per_person=price, category=category_slug), admin_user)
        accommodations = [
            ("Sea View Room Upgrade", "Upgrade to a sea-facing room in Kaikoura.", 60, "room_upgrade"),
            ("Extra Night in Queenstown", "Add one additional night at tour end, room only.", 180, "additional_night"),
        ]
        for name, description, price, category_slug in accommodations:
            tour_services.create_accommodation(db, tour_id, AccommodationExtraPayload(accommodation_name=name, description=description, extra_price=price, category=category_slug), admin_user)
        print(f"  {len(activities)} optional activities, {len(accommodations)} accommodation extras added")

        # 9. Extension (links to another existing tour) ----------------------
        if extension_target and extension_target.id != tour_id:
            tour_services.create_extension(db, tour_id, ExtensionPayload(
                extension_tour_id=extension_target.id,
                extension_title=f"Extend with: {extension_target.title}",
                extension_note="Add this tour on to your itinerary for a discounted combined rate.",
                extra_price=350,
            ), admin_user)
            print(f"  1 extension linked to tour #{extension_target.id}")

        # 10. Calendar departures (some low-stock, to exercise "Seats Left") ----
        now = datetime.now(timezone.utc)
        departures = [
            (now + timedelta(days=21), 16),
            (now + timedelta(days=35), 4),
            (now + timedelta(days=49), 16),
            (now + timedelta(days=63), 2),
        ]
        for date, seats in departures:
            tour_services.create_calendar_entry(db, tour_id, CalendarPayload(tour_date=date, available_seats=seats, status="available"), admin_user)
        print(f"  {len(departures)} calendar departures added")

        # 11. Discount (drives the "You Save" banner) --------------------------
        tour_services.create_discount(db, tour_id, DiscountPayload(
            discount_name="Early Bird 10% Off",
            discount_code="NZEARLY10",
            discount_type="percentage",
            discount_value=10,
            discount_scope="tour",
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=90),
        ), admin_user)
        print("  1 active discount added")

        # 12. Publish -----------------------------------------------------------
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
