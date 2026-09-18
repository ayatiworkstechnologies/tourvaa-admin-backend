"""Seed the default tour categories and subcategories.

Safe to run repeatedly: records are matched by slug and existing content is
updated, never deleted. Run from the backend root with:
    python -m scripts.seed_tour_catalog
"""

# Import the application once so SQLAlchemy registers every related model
# (Tour has relationships to Supplier, Country, and other modules).
import app.main  # noqa: F401

from app.database import SessionLocal
from app.models.cms import TourCategory, TourSubcategory


CATALOG = {
    "Adventure Tours": ["Hiking & Trekking", "Wildlife Safaris", "Water Adventures", "Outdoor Activities"],
    "Luxury Tours": ["Luxury Escapes", "Private Tours", "Luxury Cruises", "Premium Experiences"],
    "Cultural Tours": ["Heritage & History", "Arts & Traditions", "Food & Culinary", "Local Experiences"],
    "Family Tours": ["Family Holidays", "Educational Trips", "Theme Parks", "Family Activities"],
    "Beach & Island Tours": ["Island Hopping", "Beach Holidays", "Snorkelling & Diving", "Water Sports"],
    "City Breaks": ["City Sightseeing", "Shopping Tours", "Nightlife & Entertainment", "Architecture & Museums"],
    "Wellness Tours": ["Spa & Relaxation", "Yoga Retreats", "Health & Fitness", "Mindfulness Retreats"],
    "Romantic Tours": ["Honeymoon Packages", "Couples Getaways", "Anniversary Trips", "Romantic Experiences"],
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
            else:
                category.category_name = category_name
                category.status = "active"
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
                else:
                    item.category_id = category.id
                    item.subcategory_name = name
                    item.status = "active"
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
