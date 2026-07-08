from math import ceil
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.modules.common.money import utcnow
from app.modules.website_cms.models import (
    Blog, CmsPolicy, CustomerReview, ExternalLink, HelpCentreArticle,
    HomepageBanner, PopularDestination, PopularTour, PromotionalPopup,
    SitemapEntry, TourOnDeal,
)
from app.modules.website_cms.schemas import (
    BannerPayload, BlogPayload, ExternalLinkPayload, HelpArticlePayload,
    PolicyPayload, PopularDestinationPayload, PopularTourPayload,
    PopupPayload, ReviewPayload, SitemapEntryPayload, TourOnDealPayload,
)


def _paginate(q, page: int, limit: int, serializer) -> dict:
    total = q.count()
    items = [serializer(r) for r in q.offset((page - 1) * limit).limit(limit).all()]
    return {"items": items, "data": items, "total": total, "page": page, "limit": limit, "total_pages": max(1, ceil(total / limit))}


def _get_or_404(db, model, item_id: int, label: str):
    obj = db.query(model).filter(model.id == item_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return obj


# serializers

def _s_banner(r: HomepageBanner): return {"id": r.id, "title": r.title, "subtitle": r.subtitle, "image": r.image, "cta_text": r.cta_text, "cta_url": r.cta_url, "sort_order": r.sort_order, "is_active": r.is_active, "created_at": r.created_at, "updated_at": r.updated_at}
def _s_dest(r: PopularDestination): return {"id": r.id, "country_id": r.country_id, "city_id": r.city_id, "title": r.title, "image": r.image, "description": r.description, "sort_order": r.sort_order, "is_active": r.is_active, "created_at": r.created_at}
def _s_popular_tour(r: PopularTour): return {"id": r.id, "tour_id": r.tour_id, "sort_order": r.sort_order, "is_active": r.is_active, "created_at": r.created_at}
def _s_deal(r: TourOnDeal): return {"id": r.id, "tour_id": r.tour_id, "deal_label": r.deal_label, "discount_percentage": r.discount_percentage, "valid_until": r.valid_until, "sort_order": r.sort_order, "is_active": r.is_active, "created_at": r.created_at}
def _s_blog(r: Blog): return {"id": r.id, "title": r.title, "slug": r.slug, "excerpt": r.excerpt, "content": r.content, "featured_image": r.featured_image, "author": r.author, "tags": r.tags, "seo_title": r.seo_title, "seo_description": r.seo_description, "status": r.status, "published_at": r.published_at, "created_at": r.created_at, "updated_at": r.updated_at}
def _s_review(r: CustomerReview): return {"id": r.id, "reviewer_name": r.reviewer_name, "reviewer_image": r.reviewer_image, "rating": r.rating, "review_text": r.review_text, "tour_name": r.tour_name, "country": r.country, "sort_order": r.sort_order, "is_active": r.is_active, "created_at": r.created_at}
def _s_help(r: HelpCentreArticle): return {"id": r.id, "category": r.category, "question": r.question, "answer": r.answer, "sort_order": r.sort_order, "is_active": r.is_active, "created_at": r.created_at}
def _s_policy(r: CmsPolicy): return {"id": r.id, "slug": r.slug, "title": r.title, "content": r.content, "last_updated": r.last_updated, "created_at": r.created_at, "updated_at": r.updated_at}
def _s_popup(r: PromotionalPopup): return {"id": r.id, "title": r.title, "content": r.content, "image": r.image, "cta_text": r.cta_text, "cta_url": r.cta_url, "display_after_seconds": r.display_after_seconds, "display_frequency": r.display_frequency, "is_active": r.is_active, "valid_from": r.valid_from, "valid_until": r.valid_until, "created_at": r.created_at}
def _s_link(r: ExternalLink): return {"id": r.id, "label": r.label, "url": r.url, "open_in_new_tab": r.open_in_new_tab, "location": r.location, "sort_order": r.sort_order, "is_active": r.is_active, "created_at": r.created_at}
def _s_sitemap(r: SitemapEntry): return {"id": r.id, "url": r.url, "change_frequency": r.change_frequency, "priority": r.priority, "last_modified": r.last_modified, "is_active": r.is_active, "created_at": r.created_at}


# generic crud factory

def _list(db, model, serializer, page, limit, active_only=False):
    q = db.query(model)
    if active_only:
        q = q.filter(model.is_active == True)
    q = q.order_by(model.sort_order.asc() if hasattr(model, "sort_order") else model.id.desc())
    return _paginate(q, page, limit, serializer)


def _create(db, model, payload_dict, serializer):
    obj = model(**payload_dict)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return serializer(obj)


def _update(db, model, item_id, payload_dict, serializer, label):
    obj = _get_or_404(db, model, item_id, label)
    for k, v in payload_dict.items():
        if v is not None or k in payload_dict:
            setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return serializer(obj)


def _delete(db, model, item_id, label):
    obj = _get_or_404(db, model, item_id, label)
    db.delete(obj)
    db.commit()


# banners

def list_banners(db, page, limit, active_only=False): return _list(db, HomepageBanner, _s_banner, page, limit, active_only)
def create_banner(db, data: BannerPayload): return _create(db, HomepageBanner, data.model_dump(), _s_banner)
def update_banner(db, item_id, data: BannerPayload): return _update(db, HomepageBanner, item_id, data.model_dump(exclude_unset=True), _s_banner, "Banner")
def delete_banner(db, item_id): _delete(db, HomepageBanner, item_id, "Banner")

# popular destinations

def list_destinations(db, page, limit, active_only=False): return _list(db, PopularDestination, _s_dest, page, limit, active_only)
def create_destination(db, data: PopularDestinationPayload): return _create(db, PopularDestination, data.model_dump(), _s_dest)
def update_destination(db, item_id, data: PopularDestinationPayload): return _update(db, PopularDestination, item_id, data.model_dump(exclude_unset=True), _s_dest, "Destination")
def delete_destination(db, item_id): _delete(db, PopularDestination, item_id, "Destination")

# popular tours

def list_popular_tours(db, page, limit): return _list(db, PopularTour, _s_popular_tour, page, limit)
def create_popular_tour(db, data: PopularTourPayload): return _create(db, PopularTour, data.model_dump(), _s_popular_tour)
def delete_popular_tour(db, item_id): _delete(db, PopularTour, item_id, "Popular Tour")

# tours on deals

def list_deals(db, page, limit, active_only=False): return _list(db, TourOnDeal, _s_deal, page, limit, active_only)
def create_deal(db, data: TourOnDealPayload): return _create(db, TourOnDeal, data.model_dump(), _s_deal)
def update_deal(db, item_id, data: TourOnDealPayload): return _update(db, TourOnDeal, item_id, data.model_dump(exclude_unset=True), _s_deal, "Deal")
def delete_deal(db, item_id): _delete(db, TourOnDeal, item_id, "Deal")

# blogs

def _slugify_blog(title: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")

def list_blogs(db, page, limit, active_only=False):
    q = db.query(Blog)
    if active_only:
        q = q.filter(Blog.status == "published")
    q = q.order_by(Blog.id.desc())
    return _paginate(q, page, limit, _s_blog)

def create_blog(db, data: BlogPayload):
    d = data.model_dump()
    if not d.get("slug"):
        d["slug"] = _slugify_blog(data.title)
    if data.status == "published" and not d.get("published_at"):
        d["published_at"] = utcnow()
    return _create(db, Blog, d, _s_blog)

def update_blog(db, item_id, data: BlogPayload):
    d = data.model_dump(exclude_unset=True)
    if d.get("status") == "published":
        blog = db.query(Blog).filter(Blog.id == item_id).first()
        if blog and not blog.published_at:
            d["published_at"] = utcnow()
    return _update(db, Blog, item_id, d, _s_blog, "Blog")

def delete_blog(db, item_id): _delete(db, Blog, item_id, "Blog")
def get_blog(db, item_id): return _s_blog(_get_or_404(db, Blog, item_id, "Blog"))

# customer reviews

def list_reviews(db, page, limit, active_only=False): return _list(db, CustomerReview, _s_review, page, limit, active_only)
def create_review(db, data: ReviewPayload): return _create(db, CustomerReview, data.model_dump(), _s_review)
def update_review(db, item_id, data: ReviewPayload): return _update(db, CustomerReview, item_id, data.model_dump(exclude_unset=True), _s_review, "Review")
def delete_review(db, item_id): _delete(db, CustomerReview, item_id, "Review")

# help centre

def list_help(db, page, limit, category: str = "", active_only=False):
    q = db.query(HelpCentreArticle)
    if active_only:
        q = q.filter(HelpCentreArticle.is_active == True)
    if category:
        q = q.filter(HelpCentreArticle.category == category)
    q = q.order_by(HelpCentreArticle.sort_order, HelpCentreArticle.id)
    return _paginate(q, page, limit, _s_help)

def create_help(db, data: HelpArticlePayload): return _create(db, HelpCentreArticle, data.model_dump(), _s_help)
def update_help(db, item_id, data: HelpArticlePayload): return _update(db, HelpCentreArticle, item_id, data.model_dump(exclude_unset=True), _s_help, "Help Article")
def delete_help(db, item_id): _delete(db, HelpCentreArticle, item_id, "Help Article")

# policies

def list_policies(db, page, limit): return _list(db, CmsPolicy, _s_policy, page, limit)

def get_policy_by_slug(db, slug: str):
    obj = db.query(CmsPolicy).filter(CmsPolicy.slug == slug).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Policy not found")
    return _s_policy(obj)

def upsert_policy(db, data: PolicyPayload):
    obj = db.query(CmsPolicy).filter(CmsPolicy.slug == data.slug).first()
    if obj:
        obj.title = data.title
        obj.content = data.content
        obj.last_updated = utcnow()
    else:
        obj = CmsPolicy(slug=data.slug, title=data.title, content=data.content, last_updated=utcnow())
        db.add(obj)
    db.commit()
    db.refresh(obj)
    return _s_policy(obj)

# promotional popups

def list_popups(db, page, limit, active_only=False): return _list(db, PromotionalPopup, _s_popup, page, limit, active_only)
def create_popup(db, data: PopupPayload): return _create(db, PromotionalPopup, data.model_dump(), _s_popup)
def update_popup(db, item_id, data: PopupPayload): return _update(db, PromotionalPopup, item_id, data.model_dump(exclude_unset=True), _s_popup, "Popup")
def delete_popup(db, item_id): _delete(db, PromotionalPopup, item_id, "Popup")

# external links

def list_external_links(db, page, limit, location: str = ""):
    q = db.query(ExternalLink)
    if location:
        q = q.filter(ExternalLink.location == location)
    q = q.order_by(ExternalLink.sort_order, ExternalLink.id)
    return _paginate(q, page, limit, _s_link)

def create_external_link(db, data: ExternalLinkPayload): return _create(db, ExternalLink, data.model_dump(), _s_link)
def update_external_link(db, item_id, data: ExternalLinkPayload): return _update(db, ExternalLink, item_id, data.model_dump(exclude_unset=True), _s_link, "External Link")
def delete_external_link(db, item_id): _delete(db, ExternalLink, item_id, "External Link")

# sitemap

def list_sitemap(db, page, limit): return _list(db, SitemapEntry, _s_sitemap, page, limit)
def create_sitemap_entry(db, data: SitemapEntryPayload): return _create(db, SitemapEntry, data.model_dump(), _s_sitemap)
def update_sitemap_entry(db, item_id, data: SitemapEntryPayload): return _update(db, SitemapEntry, item_id, data.model_dump(exclude_unset=True), _s_sitemap, "Sitemap Entry")
def delete_sitemap_entry(db, item_id): _delete(db, SitemapEntry, item_id, "Sitemap Entry")

def get_sitemap_xml(db) -> str:
    entries = db.query(SitemapEntry).filter(SitemapEntry.is_active == True).all()
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for e in entries:
        lm = e.last_modified.strftime("%Y-%m-%d") if e.last_modified else ""
        lines.append(f"  <url><loc>{e.url}</loc><changefreq>{e.change_frequency}</changefreq><priority>{e.priority}</priority>{'<lastmod>' + lm + '</lastmod>' if lm else ''}</url>")
    lines.append("</urlset>")
    return "\n".join(lines)
