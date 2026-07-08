from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Table, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Country(Base):
    __tablename__ = "countries"

    id = Column(Integer, primary_key=True, index=True)
    country_name = Column(String(120), nullable=False, unique=True)
    country_code = Column(String(10), nullable=False, unique=True)
    phone_code = Column(String(10), default="", nullable=False)
    currency_code = Column(String(10), default="", nullable=False)
    status = Column(String(20), default="active", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    states = relationship("State", back_populates="country")
    cities = relationship("City", back_populates="country")


class State(Base):
    __tablename__ = "states"

    id = Column(Integer, primary_key=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False, index=True)
    state_name = Column(String(150), nullable=False)
    state_code = Column(String(10), default="", nullable=False)
    status = Column(String(20), default="active", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    country = relationship("Country", back_populates="states")
    cities = relationship("City", back_populates="state")


class City(Base):
    __tablename__ = "cities"

    id = Column(Integer, primary_key=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False, index=True)
    state_id = Column(Integer, ForeignKey("states.id"), nullable=True, index=True)
    city_name = Column(String(120), nullable=False)
    status = Column(String(20), default="active", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    country = relationship("Country", back_populates="cities")
    state = relationship("State", back_populates="cities")


class TourCategory(Base):
    __tablename__ = "tour_categories"

    id = Column(Integer, primary_key=True, index=True)
    category_name = Column(String(120), nullable=False)
    slug = Column(String(150), nullable=False, unique=True, index=True)
    description = Column(Text, default="", nullable=False)
    image = Column(String(255), default="", nullable=False)
    status = Column(String(20), default="active", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    subcategories = relationship("TourSubcategory", back_populates="category")


class TourSubcategory(Base):
    __tablename__ = "tour_subcategories"

    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(Integer, ForeignKey("tour_categories.id"), nullable=False, index=True)
    subcategory_name = Column(String(120), nullable=False)
    slug = Column(String(150), nullable=False, unique=True, index=True)
    description = Column(Text, default="", nullable=False)
    image = Column(String(255), default="", nullable=False)
    status = Column(String(20), default="active", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    category = relationship("TourCategory", back_populates="subcategories")


class TourSubcategoryMap(Base):
    __tablename__ = "tour_subcategory_map"

    id = Column(Integer, primary_key=True, index=True)
    tour_id = Column(Integer, ForeignKey("tours.id"), nullable=False, index=True)
    subcategory_id = Column(Integer, ForeignKey("tour_subcategories.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    subcategory = relationship("TourSubcategory")


class Tour(Base):
    __tablename__ = "tours"

    id = Column(Integer, primary_key=True, index=True)
    tour_code = Column(String(30), unique=True, nullable=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True, index=True)
    title = Column(String(180), nullable=False)
    slug = Column(String(200), nullable=False, unique=True, index=True)
    subtitle = Column(String(255), default="", nullable=False)
    price_start_per_person = Column(Float, default=0, nullable=False)
    currency = Column(String(10), default="USD", nullable=False)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=True, index=True)
    city_id = Column(Integer, ForeignKey("cities.id"), nullable=True, index=True)
    category_id = Column(Integer, ForeignKey("tour_categories.id"), nullable=True, index=True)
    start_location = Column(String(150), default="", nullable=False)
    finish_location = Column(String(150), default="", nullable=False)
    number_of_days = Column(Integer, default=1, nullable=False)
    number_of_hours = Column(Integer, nullable=True)
    short_description = Column(Text, default="", nullable=False)
    long_description = Column(Text, default="", nullable=False)
    seo_title = Column(String(180), default="", nullable=False)
    seo_description = Column(String(255), default="", nullable=False)
    seo_keywords = Column(String(255), default="", nullable=False)
    image_alt_text = Column(String(180), default="", nullable=False)
    banner_image = Column(String(255), default="", nullable=False)
    map_image = Column(String(255), default="", nullable=False)
    status = Column(String(20), default="draft", nullable=False, index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    supplier = relationship("Supplier")
    country = relationship("Country")
    city = relationship("City")
    category = relationship("TourCategory")
    subcategory_links = relationship("TourSubcategoryMap", cascade="all, delete-orphan")
