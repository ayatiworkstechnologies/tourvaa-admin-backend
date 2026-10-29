"""Seed the default tour categories and subcategories.

Safe to run repeatedly: records are matched by slug. Existing records and
their admin-managed content are preserved. Run from the backend root with:
    python -m scripts.seed_tour_catalog
"""

# Import the application once so SQLAlchemy registers every related model
# (Tour has relationships to Supplier, Country, and other modules).
import app.main  # noqa: F401

from app.database import SessionLocal
from app.models.cms import TourCategory, TourSubcategory


CATALOG = {
    "Adventure Tours": ["Trekking & Hiking", "Camping", "Mountain Climbing", "Rafting", "Scuba Diving", "Safari Adventures", "Ziplining"],
    "Cultural & Heritage Tours": ["Historical Tours", "Heritage Walks", "Temple Tours", "Museum Tours", "Architecture Tours", "Local Culture"],
    "Nature & Wildlife Tours": ["Wildlife Safaris", "National Parks", "Bird Watching", "Nature Walks", "Rainforest Tours", "Eco Tours"],
    "Beach & Island Tours": ["Beach Holidays", "Island Hopping", "Snorkeling", "Coastal Tours", "Water Sports", "Beach Resorts"],
    "Hill Station & Mountain Tours": ["Hill Station Holidays", "Mountain Escapes", "Scenic Drives", "Snow Experiences", "Valley Tours"],
    "Pilgrimage & Spiritual Tours": ["Temple Visits", "Religious Pilgrimages", "Sacred Sites", "Spiritual Retreats", "Meditation Tours"],
    "Family & Leisure Tours": ["Family Holidays", "Theme Parks", "Leisure Getaways", "Kids-Friendly Tours", "Resort Holidays"],
    "Honeymoon & Romantic Tours": ["Honeymoon Packages", "Romantic Getaways", "Private Couple Tours", "Luxury Retreats"],
    "Luxury & Premium Tours": ["Luxury Holidays", "Private Guided Tours", "Premium Resorts", "VIP Experiences", "Luxury Cruises"],
    "City & Sightseeing Tours": ["City Tours", "Walking Tours", "Hop-On Hop-Off Tours", "Landmark Visits", "Night Tours"],
    "Food & Culinary Tours": ["Street Food Tours", "Local Cuisine", "Cooking Classes", "Food Tasting", "Farm-to-Table Experiences"],
    "Wellness & Retreat Tours": ["Yoga Retreats", "Ayurveda Retreats", "Spa Holidays", "Meditation Retreats", "Wellness Escapes"],
    "Cruise & Water Tours": ["River Cruises", "Houseboat Tours", "Sunset Cruises", "Boat Trips", "Yacht Experiences"],
    "Road Trips & Scenic Tours": ["Road Trips", "Self-Drive Tours", "Scenic Routes", "Motorcycle Tours", "Countryside Tours"],
    "Educational & Group Tours": ["School Tours", "College Trips", "Study Tours", "Corporate Outings", "Team Building", "Group Excursions"],
    "Festival & Special Event Tours": ["Cultural Festivals", "Seasonal Celebrations", "Music Festivals", "Local Events", "Festival Experiences"],
    "Photography & Exploration Tours": ["Wildlife Photography", "Landscape Photography", "Cultural Photography", "Offbeat Exploration"],
    "Short Trips & Weekend Getaways": ["Day Trips", "Weekend Trips", "Overnight Tours", "2–3 Day Getaways", "Local Excursions"],
}

# These are only the legacy defaults previously supplied by this seed script.
# Deactivation removes them from selection/public results while preserving old
# tour references and administrator-created taxonomy records.
LEGACY_CATEGORY_SLUGS = {
    "luxury-tours", "cultural-tours", "family-tours", "city-breaks", "wellness-tours",
    "romantic-tours", "wildlife-and-nature-tours", "heritage-and-historical-tours",
    "desert-tours", "backwater-and-houseboat-tours", "festival-and-event-tours",
    "cruise-and-river-tours", "rail-and-road-trips", "group-tours", "seasonal-tours",
}


def slugify(value: str) -> str:
    return "-".join(value.lower().replace("&", "and").split())


def run() -> None:
    db = SessionLocal()
    try:
        category_count = 0
        subcategory_count = 0
        for category_name, subcategory_names in CATALOG.items():
            category_slug = slugify(category_name)
            category = db.query(TourCategory).filter(TourCategory.slug == category_slug).first()
            if category is None:
                category = TourCategory(category_name=category_name, slug=category_slug, status="active")
                db.add(category)
                db.flush()
            category_count += 1

            for name in subcategory_names:
                slug = slugify(f"{category_name}-{name}")
                item = db.query(TourSubcategory).filter(TourSubcategory.slug == slug).first()
                if item is None:
                    db.add(TourSubcategory(
                        category_id=category.id,
                        subcategory_name=name,
                        slug=slug,
                        status="active",
                    ))
                subcategory_count += 1
        desired_category_slugs = {slugify(name) for name in CATALOG}
        desired_subcategory_slugs = {
            slugify(f"{category}-{subcategory}")
            for category, subcategories in CATALOG.items()
            for subcategory in subcategories
        }
        managed_category_slugs = desired_category_slugs | LEGACY_CATEGORY_SLUGS
        for category in db.query(TourCategory).filter(TourCategory.slug.in_(managed_category_slugs)):
            category.status = "active" if category.slug in desired_category_slugs else "inactive"
        for subcategory in db.query(TourSubcategory).join(TourCategory).filter(TourCategory.slug.in_(managed_category_slugs)):
            subcategory.status = "active" if subcategory.slug in desired_subcategory_slugs else "inactive"
        db.commit()
        print(f"Seeded {category_count} tour categories and {subcategory_count} subcategories.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run()
