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
    "Adventure Tours": ["Hiking & Trekking", "Wildlife Safaris", "Water Adventures", "Outdoor Activities", "Mountaineering", "Camping", "River Rafting", "Paragliding", "Desert Adventures", "Cycling Tours"],
    "Luxury Tours": ["Luxury Escapes", "Private Tours", "Luxury Cruises", "Premium Experiences"],
    "Cultural Tours": ["Heritage & History", "Arts & Traditions", "Food & Culinary", "Local Experiences", "Village & Rural Experiences", "Festivals & Fairs", "Handicrafts & Textiles", "Tribal Culture"],
    "Family Tours": ["Family Holidays", "Educational Trips", "Theme Parks", "Family Activities"],
    "Beach & Island Tours": ["Island Hopping", "Beach Holidays", "Snorkelling & Diving", "Water Sports"],
    "City Breaks": ["City Sightseeing", "Shopping Tours", "Nightlife & Entertainment", "Architecture & Museums"],
    "Wellness Tours": ["Spa & Relaxation", "Yoga Retreats", "Health & Fitness", "Mindfulness Retreats", "Ayurveda Retreats", "Meditation Retreats", "Naturopathy Retreats"],
    "Romantic Tours": ["Honeymoon Packages", "Couples Getaways", "Anniversary Trips", "Romantic Experiences"],
    "Pilgrimage & Spiritual Tours": ["Temple Tours", "Char Dham Yatra", "Jyotirlinga Tours", "Buddhist Pilgrimage", "Sikh Pilgrimage", "Jain Pilgrimage", "Church Pilgrimage", "Sufi & Islamic Heritage", "Sacred Rivers & Ghats", "Ashrams & Spiritual Retreats"],
    "Wildlife & Nature Tours": ["National Parks", "Tiger Safaris", "Birdwatching", "Elephant Safaris", "Forest & Jungle Tours", "Nature & Eco Tours"],
    "Heritage & Historical Tours": ["UNESCO World Heritage Sites", "Forts & Palaces", "Ancient Monuments", "Royal Heritage", "Colonial Heritage", "Archaeological Sites"],
    "Hill Station & Mountain Tours": ["Himalayan Getaways", "Hill Station Holidays", "Scenic Mountain Drives", "Snow Holidays", "Tea Plantation Stays"],
    "Desert Tours": ["Desert Safaris", "Camel Safaris", "Desert Camping", "Desert Villages & Culture"],
    "Backwater & Houseboat Tours": ["Kerala Backwaters", "Houseboat Stays", "Lake Cruises", "Village Waterways"],
    "Food & Culinary Tours": ["Street Food Tours", "Regional Cuisine", "Cooking Classes", "Spice Plantation Tours", "Tea & Coffee Experiences"],
    "Festival & Event Tours": ["Diwali Experiences", "Holi Experiences", "Onam Experiences", "Durga Puja Experiences", "Pushkar Fair", "Cultural Festivals"],
    "Cruise & River Tours": ["River Cruises", "Coastal Cruises", "Sunset Cruises", "Luxury Cruises"],
    "Rail & Road Trips": ["Heritage Rail Journeys", "Luxury Train Journeys", "Scenic Road Trips", "Motorcycle Tours"],
    "Group Tours": ["Small Group Tours", "Senior Tours", "Women Only Tours", "Student Group Tours"],
    "Seasonal Tours": ["Summer Holidays", "Monsoon Getaways", "Winter Holidays", "Spring Holidays"],
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
        db.commit()
        print(f"Seeded {category_count} tour categories and {subcategory_count} subcategories.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run()
