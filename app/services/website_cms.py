import re
from math import ceil
from typing import Optional

import bleach
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.utils.money import utcnow
from app.models.cms import Country, Tour
from app.models.website_cms import (
    Blog, CmsPage, CmsPolicy, CountryPage, CustomerReview, ExternalLink,
    FavouriteCountryEntry, FooterLink, FooterSection, HandpickedTour,
    HelpCentreArticle, HomepageBanner, HomepageContentBlock,
    PopularDestination, PopularTour, PromotionalPopup, SitemapEntry,
    TourOnDeal,
)
from app.schemas.website_cms import (
    BannerPayload, BlogPayload, CmsPagePayload, ContentBlockPayload,
    CountryPagePayload, ExternalLinkPayload, FavouriteCountryPayload,
    FooterLinkPayload, FooterSectionPayload, HandpickedTourPayload,
    HelpArticlePayload, PolicyPayload, PopularDestinationPayload,
    PopularTourPayload, PopupPayload, ReviewPayload, SitemapEntryPayload,
    TourOnDealPayload,
)

# The only keys HomepageContentBlock rows may use - keeps the generic
# key/JSON store from accumulating arbitrary, unrendered keys over time.
ALLOWED_CONTENT_BLOCK_KEYS = {
    "hero_extras", "about_section", "blog_teaser", "airport_transfer",
    "travel_support", "newsletter_banner", "top_deals_section",
    "trending_section", "favourite_countries_section",
}

# Per-country destination guide content (best time to visit, monsoon/season
# info, temperature, best places, why-visit, travel info) - one block per
# country, keyed dynamically by slug rather than a fixed key, so this can't
# be a plain set membership check like the keys above. Backs the /destinations
# /{slug} page and its admin editor (CountryDestinationInfoPanel).
_COUNTRY_INFO_KEY_RE = re.compile(r"^country_info_[a-z0-9-]{1,45}$")


def _is_allowed_content_block_key(key: str) -> bool:
    return key in ALLOWED_CONTENT_BLOCK_KEYS or bool(_COUNTRY_INFO_KEY_RE.fullmatch(key))


def _paginate(q, page: int, limit: int, serializer) -> dict:
    total = q.count()
    rows = q.offset((page - 1) * limit).limit(limit).all()
    items = []
    for row in rows:
        try:
            items.append(serializer(row))
        except TypeError:
            items.append(serializer(row, q.session))
    return {"items": items, "total": total, "page": page, "limit": limit, "total_pages": max(1, ceil(total / limit))}


def _get_or_404(db, model, item_id: int, label: str):
    obj = db.query(model).filter(model.id == item_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return obj


# Rich-text fields (blog/policy/popup content) get sanitized at write time,
# not just escaped - these are meant to render as real HTML on the public
# site, so anyone holding a CMS edit permission (not necessarily
# super-admin) could otherwise plant stored XSS for every site visitor.
_ALLOWED_HTML_TAGS = [
    "p", "br", "strong", "b", "em", "i", "u", "s",
    "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "a", "img", "span", "div", "table", "thead",
    "tbody", "tr", "th", "td", "hr", "figure", "figcaption",
]
_ALLOWED_HTML_ATTRS = {
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "title", "width", "height"],
    "span": ["class"],
    "div": ["class"],
    "table": ["class"],
    "td": ["colspan", "rowspan"],
    "th": ["colspan", "rowspan"],
}
_ALLOWED_HTML_PROTOCOLS = ["http", "https", "mailto"]


def _sanitize_html(value: Optional[str]) -> Optional[str]:
    if not value:
        return value
    return bleach.clean(
        value,
        tags=_ALLOWED_HTML_TAGS,
        attributes=_ALLOWED_HTML_ATTRS,
        protocols=_ALLOWED_HTML_PROTOCOLS,
        strip=True,
    )


# serializers

def _s_banner(r: HomepageBanner): return {"id": r.id, "title": r.title, "subtitle": r.subtitle, "image": r.image, "video": r.video, "cta_text": r.cta_text, "cta_url": r.cta_url, "sort_order": r.sort_order, "is_active": r.is_active, "created_at": r.created_at, "updated_at": r.updated_at}
def _s_dest(r: PopularDestination): return {"id": r.id, "country_id": r.country_id, "city_id": r.city_id, "title": r.title, "image": r.image, "description": r.description, "sort_order": r.sort_order, "is_active": r.is_active, "created_at": r.created_at}
def _tour_label(db: Session, tour_id: int):
    tour = db.query(Tour).filter(Tour.id == tour_id).first()
    if not tour:
        return {"tour_title": "", "tour_code": ""}
    return {"tour_title": tour.title, "tour_code": tour.tour_code}


def _s_popular_tour(r: PopularTour, db: Session | None = None):
    tour = _tour_label(db, r.tour_id) if db else {"tour_title": "", "tour_code": ""}
    return {"id": r.id, "tour_id": r.tour_id, **tour, "sort_order": r.sort_order, "is_active": r.is_active, "created_at": r.created_at}
def _s_deal(r: TourOnDeal, db: Session | None = None):
    tour = _tour_label(db, r.tour_id) if db else {"tour_title": "", "tour_code": ""}
    return {"id": r.id, "tour_id": r.tour_id, **tour, "deal_label": r.deal_label, "discount_percentage": r.discount_percentage, "valid_until": r.valid_until, "sort_order": r.sort_order, "is_active": r.is_active, "created_at": r.created_at}
def _s_blog(r: Blog): return {"id": r.id, "title": r.title, "slug": r.slug, "excerpt": r.excerpt, "content": r.content, "featured_image": r.featured_image, "author": r.author, "tags": r.tags, "seo_title": r.seo_title, "seo_description": r.seo_description, "status": r.status, "published_at": r.published_at, "created_at": r.created_at, "updated_at": r.updated_at}
def _s_cms_page(r: CmsPage): return {"id": r.id, "title": r.title, "slug": r.slug, "content": r.content, "seo_title": r.seo_title, "seo_description": r.seo_description, "status": r.status, "footer_section_id": r.footer_section_id, "sort_order": r.sort_order, "created_at": r.created_at, "updated_at": r.updated_at}
def _s_review(r: CustomerReview): return {"id": r.id, "reviewer_name": r.reviewer_name, "reviewer_image": r.reviewer_image, "rating": r.rating, "review_text": r.review_text, "tour_name": r.tour_name, "country": r.country, "sort_order": r.sort_order, "is_active": r.is_active, "created_at": r.created_at}
def _s_help(r: HelpCentreArticle): return {"id": r.id, "category": r.category, "question": r.question, "answer": r.answer, "sort_order": r.sort_order, "is_active": r.is_active, "created_at": r.created_at}
def _s_policy(r: CmsPolicy): return {"id": r.id, "slug": r.slug, "title": r.title, "content": r.content, "last_updated": r.last_updated, "created_at": r.created_at, "updated_at": r.updated_at}
def _s_popup(r: PromotionalPopup): return {"id": r.id, "title": r.title, "content": r.content, "image": r.image, "cta_text": r.cta_text, "cta_url": r.cta_url, "display_after_seconds": r.display_after_seconds, "display_frequency": r.display_frequency, "is_active": r.is_active, "valid_from": r.valid_from, "valid_until": r.valid_until, "created_at": r.created_at}
def _s_link(r: ExternalLink): return {"id": r.id, "label": r.label, "url": r.url, "open_in_new_tab": r.open_in_new_tab, "location": r.location, "sort_order": r.sort_order, "is_active": r.is_active, "created_at": r.created_at}
def _s_footer_link(r: FooterLink): return {"id": r.id, "section_id": r.section_id, "label": r.label, "url": r.url, "open_in_new_tab": r.open_in_new_tab, "sort_order": r.sort_order, "is_active": r.is_active, "created_at": r.created_at, "updated_at": r.updated_at}
def _s_footer_section(r: FooterSection, include_links: bool = False):
    data = {"id": r.id, "title": r.title, "sort_order": r.sort_order, "is_active": r.is_active, "created_at": r.created_at, "updated_at": r.updated_at}
    if include_links:
        data["links"] = [_s_footer_link(link) for link in r.links]
    return data
def _s_sitemap(r: SitemapEntry): return {"id": r.id, "url": r.url, "change_frequency": r.change_frequency, "priority": r.priority, "last_modified": r.last_modified, "is_active": r.is_active, "created_at": r.created_at}
def _s_handpicked(r: HandpickedTour, db: Session | None = None):
    tour = _tour_label(db, r.tour_id) if db else {"tour_title": "", "tour_code": ""}
    return {"id": r.id, "tour_id": r.tour_id, **tour, "sort_order": r.sort_order, "is_active": r.is_active, "created_at": r.created_at}
def _s_favourite_country(r: FavouriteCountryEntry): return {"id": r.id, "country_id": r.country_id, "title": r.title, "snippet": r.snippet, "image": r.image, "href": r.href, "sort_order": r.sort_order, "is_active": r.is_active, "created_at": r.created_at}
def _s_content_block(r: HomepageContentBlock | None, key: str): return {"key": key, "data": r.data if r else {}, "updated_at": r.updated_at if r else None}
def _s_country_page(r: CountryPage, db: Session | None = None):
    country_name = None
    if db is not None:
        country = db.query(Country).filter(Country.id == r.country_id).first()
        country_name = country.country_name if country else None
    return {"id": r.id, "country_id": r.country_id, "country_name": country_name, "hero_title": r.hero_title, "hero_description": r.hero_description, "hero_image": r.hero_image, "showcase_title": r.showcase_title, "showcase_description": r.showcase_description, "showcase_image": r.showcase_image, "seo_title": r.seo_title, "seo_description": r.seo_description, "is_active": r.is_active, "created_at": r.created_at, "updated_at": r.updated_at}


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
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Invalid reference id (e.g. country/city/tour not found)")
    db.refresh(obj)
    return serializer(obj)


def _update(db, model, item_id, payload_dict, serializer, label):
    obj = _get_or_404(db, model, item_id, label)
    for k, v in payload_dict.items():
        if v is not None or k in payload_dict:
            setattr(obj, k, v)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Invalid reference id (e.g. country/city/tour not found)")
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

def list_popular_tours(db, page, limit, published_only=False, active_only=False):
    # published_only=True (used by the public homepage) drops rows whose
    # pinned tour is no longer published - a tour can be unpublished (or
    # deleted then id-reused) after being pinned here, and without this
    # filter the public site would try to fetch a tour it can't see,
    # 404ing needlessly. Admin's CMS list still sees every row (including
    # stale pins) so they can find and remove them.
    q = db.query(PopularTour)
    if active_only:
        q = q.filter(PopularTour.is_active == True)  # noqa: E712
    if published_only:
        q = q.join(Tour, Tour.id == PopularTour.tour_id).filter(Tour.status == "published")
    q = q.order_by(PopularTour.sort_order.asc())
    return _paginate(q, page, limit, lambda row: _s_popular_tour(row, db))
def create_popular_tour(db, data: PopularTourPayload):
    if not db.query(Tour).filter(Tour.id == data.tour_id).first():
        raise HTTPException(status_code=400, detail="Selected tour does not exist")
    obj = PopularTour(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return _s_popular_tour(obj, db)
def delete_popular_tour(db, item_id): _delete(db, PopularTour, item_id, "Popular Tour")

# tours on deals

def list_deals(db, page, limit, active_only=False, published_only=False):
    # published_only - see the comment on list_popular_tours above; same
    # stale-pin problem applies here.
    q = db.query(TourOnDeal)
    if active_only:
        q = q.filter(TourOnDeal.is_active == True)  # noqa: E712
    if published_only:
        q = q.join(Tour, Tour.id == TourOnDeal.tour_id).filter(Tour.status == "published")
    q = q.order_by(TourOnDeal.sort_order.asc())
    return _paginate(q, page, limit, lambda row: _s_deal(row, db))
def create_deal(db, data: TourOnDealPayload):
    if not db.query(Tour).filter(Tour.id == data.tour_id).first():
        raise HTTPException(status_code=400, detail="Selected tour does not exist")
    obj = TourOnDeal(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return _s_deal(obj, db)
def update_deal(db, item_id, data: TourOnDealPayload): return _update(db, TourOnDeal, item_id, data.model_dump(exclude_unset=True), _s_deal, "Deal")
def delete_deal(db, item_id): _delete(db, TourOnDeal, item_id, "Deal")

# blogs

def _slugify(title: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")

def list_blogs(db, page, limit, active_only=False, slug=""):
    q = db.query(Blog)
    if active_only:
        q = q.filter(Blog.status == "published")
    if slug:
        q = q.filter(Blog.slug == slug)
    q = q.order_by(Blog.id.desc())
    return _paginate(q, page, limit, _s_blog)

def create_blog(db, data: BlogPayload):
    d = data.model_dump()
    d["content"] = _sanitize_html(d.get("content"))
    if not d.get("slug"):
        d["slug"] = _slugify(data.title)
    if data.status == "published" and not d.get("published_at"):
        d["published_at"] = utcnow()
    return _create(db, Blog, d, _s_blog)

def update_blog(db, item_id, data: BlogPayload):
    d = data.model_dump(exclude_unset=True)
    if "content" in d:
        d["content"] = _sanitize_html(d.get("content"))
    if d.get("status") == "published":
        blog = db.query(Blog).filter(Blog.id == item_id).first()
        if blog and not blog.published_at:
            d["published_at"] = utcnow()
    return _update(db, Blog, item_id, d, _s_blog, "Blog")

def delete_blog(db, item_id): _delete(db, Blog, item_id, "Blog")
def get_blog(db, item_id): return _s_blog(_get_or_404(db, Blog, item_id, "Blog"))

# cms pages (dynamically admin-created pages, distinct from the small fixed
# set of legal documents CmsPolicy covers)

def list_cms_pages(db, page, limit, active_only=False):
    q = db.query(CmsPage)
    if active_only:
        q = q.filter(CmsPage.status == "published")
    q = q.order_by(CmsPage.sort_order, CmsPage.id.desc())
    return _paginate(q, page, limit, _s_cms_page)

def create_cms_page(db, data: CmsPagePayload):
    d = data.model_dump()
    d["content"] = _sanitize_html(d.get("content"))
    if not d.get("slug"):
        d["slug"] = _slugify(data.title)
    return _create(db, CmsPage, d, _s_cms_page)

def update_cms_page(db, item_id, data: CmsPagePayload):
    d = data.model_dump(exclude_unset=True)
    if "content" in d:
        d["content"] = _sanitize_html(d.get("content"))
    return _update(db, CmsPage, item_id, d, _s_cms_page, "Page")

def delete_cms_page(db, item_id): _delete(db, CmsPage, item_id, "Page")
def get_cms_page(db, item_id): return _s_cms_page(_get_or_404(db, CmsPage, item_id, "Page"))

def get_cms_page_by_slug(db, slug: str):
    """Public lookup - a draft page is never reachable at its URL."""
    page = db.query(CmsPage).filter(CmsPage.slug == slug, CmsPage.status == "published").first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return _s_cms_page(page)

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
    content = _sanitize_html(data.content)
    obj = db.query(CmsPolicy).filter(CmsPolicy.slug == data.slug).first()
    if obj:
        obj.title = data.title
        obj.content = content
        obj.last_updated = utcnow()
    else:
        obj = CmsPolicy(slug=data.slug, title=data.title, content=content, last_updated=utcnow())
        db.add(obj)
    db.commit()
    db.refresh(obj)
    return _s_policy(obj)

# promotional popups

def list_popups(db, page, limit, active_only=False): return _list(db, PromotionalPopup, _s_popup, page, limit, active_only)
def create_popup(db, data: PopupPayload):
    d = data.model_dump()
    d["content"] = _sanitize_html(d.get("content"))
    return _create(db, PromotionalPopup, d, _s_popup)

def update_popup(db, item_id, data: PopupPayload):
    d = data.model_dump(exclude_unset=True)
    if "content" in d:
        d["content"] = _sanitize_html(d.get("content"))
    return _update(db, PromotionalPopup, item_id, d, _s_popup, "Popup")
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

# footer sections & links

def list_footer_sections(db, page, limit): return _list(db, FooterSection, _s_footer_section, page, limit)
def create_footer_section(db, data: FooterSectionPayload): return _create(db, FooterSection, data.model_dump(), _s_footer_section)
def update_footer_section(db, item_id, data: FooterSectionPayload): return _update(db, FooterSection, item_id, data.model_dump(exclude_unset=True), _s_footer_section, "Footer Section")
def delete_footer_section(db, item_id): _delete(db, FooterSection, item_id, "Footer Section")

def list_footer_links(db, page, limit, section_id: int | None = None):
    q = db.query(FooterLink)
    if section_id is not None:
        q = q.filter(FooterLink.section_id == section_id)
    q = q.order_by(FooterLink.sort_order, FooterLink.id)
    return _paginate(q, page, limit, _s_footer_link)

def create_footer_link(db, data: FooterLinkPayload): return _create(db, FooterLink, data.model_dump(), _s_footer_link)
def update_footer_link(db, item_id, data: FooterLinkPayload): return _update(db, FooterLink, item_id, data.model_dump(exclude_unset=True), _s_footer_link, "Footer Link")
def delete_footer_link(db, item_id): _delete(db, FooterLink, item_id, "Footer Link")

def get_public_footer(db):
    """Active sections (ordered) each with their active links (ordered) - a
    single read for the public site's footer, so it never has to make one
    request per section. Each section's links are the union of hand-authored
    FooterLink rows and any published CmsPage assigned to that section
    (footer_section_id) - a page is just referenced by FK here, not
    duplicated into a FooterLink row, so editing the page is the only place
    its footer label/URL needs to change."""
    sections = (
        db.query(FooterSection)
        .filter(FooterSection.is_active == True)  # noqa: E712
        .order_by(FooterSection.sort_order, FooterSection.id)
        .all()
    )
    pages_by_section: dict[int, list[CmsPage]] = {}
    for cms_page in db.query(CmsPage).filter(CmsPage.status == "published", CmsPage.footer_section_id.isnot(None)).all():
        pages_by_section.setdefault(cms_page.footer_section_id, []).append(cms_page)

    result = []
    for section in sections:
        entries = [
            {"id": f"link-{link.id}", "label": link.label, "url": link.url, "open_in_new_tab": link.open_in_new_tab, "sort_order": link.sort_order}
            for link in section.links
            if link.is_active
        ]
        entries += [
            {"id": f"page-{cms_page.id}", "label": cms_page.title, "url": f"/{cms_page.slug}", "open_in_new_tab": False, "sort_order": cms_page.sort_order}
            for cms_page in pages_by_section.get(section.id, [])
        ]
        entries.sort(key=lambda e: (e["sort_order"], e["id"]))
        result.append({
            "id": section.id,
            "title": section.title,
            "links": [{"id": e["id"], "label": e["label"], "url": e["url"], "open_in_new_tab": e["open_in_new_tab"]} for e in entries],
        })
    return result

# sitemap

def list_sitemap(db, page, limit): return _list(db, SitemapEntry, _s_sitemap, page, limit)
def create_sitemap_entry(db, data: SitemapEntryPayload): return _create(db, SitemapEntry, data.model_dump(), _s_sitemap)
def update_sitemap_entry(db, item_id, data: SitemapEntryPayload): return _update(db, SitemapEntry, item_id, data.model_dump(exclude_unset=True), _s_sitemap, "Sitemap Entry")
def delete_sitemap_entry(db, item_id): _delete(db, SitemapEntry, item_id, "Sitemap Entry")

# handpicked tours

def list_handpicked_tours(db, page, limit, published_only=False, active_only=False):
    # Same stale-pin problem as list_popular_tours - see the comment there.
    q = db.query(HandpickedTour)
    if active_only:
        q = q.filter(HandpickedTour.is_active == True)  # noqa: E712
    if published_only:
        q = q.join(Tour, Tour.id == HandpickedTour.tour_id).filter(Tour.status == "published")
    q = q.order_by(HandpickedTour.sort_order.asc())
    return _paginate(q, page, limit, lambda row: _s_handpicked(row, db))
def create_handpicked_tour(db, data: HandpickedTourPayload):
    if not db.query(Tour).filter(Tour.id == data.tour_id).first():
        raise HTTPException(status_code=400, detail="Selected tour does not exist")
    obj = HandpickedTour(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return _s_handpicked(obj, db)
def delete_handpicked_tour(db, item_id): _delete(db, HandpickedTour, item_id, "Handpicked Tour")

# favourite countries

def list_favourite_countries(db, page, limit, active_only=False): return _list(db, FavouriteCountryEntry, _s_favourite_country, page, limit, active_only)
def create_favourite_country(db, data: FavouriteCountryPayload): return _create(db, FavouriteCountryEntry, data.model_dump(), _s_favourite_country)
def update_favourite_country(db, item_id, data: FavouriteCountryPayload): return _update(db, FavouriteCountryEntry, item_id, data.model_dump(exclude_unset=True), _s_favourite_country, "Favourite Country")
def delete_favourite_country(db, item_id): _delete(db, FavouriteCountryEntry, item_id, "Favourite Country")

# country landing pages (/tours/{country})

def list_country_pages(db, page, limit, active_only=False):
    q = db.query(CountryPage)
    if active_only:
        q = q.filter(CountryPage.is_active == True)  # noqa: E712
    q = q.order_by(CountryPage.id.desc())
    return _paginate(q, page, limit, lambda row: _s_country_page(row, db))
def create_country_page(db, data: CountryPagePayload):
    if not db.query(Country).filter(Country.id == data.country_id).first():
        raise HTTPException(status_code=400, detail="Selected country does not exist")
    obj = CountryPage(**data.model_dump())
    db.add(obj)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="This country already has a landing page")
    db.refresh(obj)
    return _s_country_page(obj, db)
def update_country_page(db, item_id, data: CountryPagePayload): return _update(db, CountryPage, item_id, data.model_dump(exclude_unset=True), lambda row: _s_country_page(row, db), "Country Page")
def delete_country_page(db, item_id): _delete(db, CountryPage, item_id, "Country Page")

def list_active_country_pages_public(db):
    # Public consumer (GET /public/country-pages): the country landing page
    # itself resolves country by name/slug (see countryMetadataFor and
    # CountryTourListing), so this returns country_name alongside each row
    # rather than requiring a second lookup.
    rows = (
        db.query(CountryPage, Country.country_name)
        .join(Country, Country.id == CountryPage.country_id)
        .filter(CountryPage.is_active == True)  # noqa: E712
        .all()
    )
    return [
        {**_s_country_page(row), "country_name": country_name}
        for row, country_name in rows
    ]

# generic homepage content blocks (see ALLOWED_CONTENT_BLOCK_KEYS above)

def get_content_block(db, key: str):
    if not _is_allowed_content_block_key(key):
        raise HTTPException(status_code=404, detail="Unknown content block")
    obj = db.query(HomepageContentBlock).filter(HomepageContentBlock.key == key).first()
    return _s_content_block(obj, key)

def upsert_content_block(db, key: str, data: ContentBlockPayload):
    if not _is_allowed_content_block_key(key):
        raise HTTPException(status_code=404, detail="Unknown content block")
    obj = db.query(HomepageContentBlock).filter(HomepageContentBlock.key == key).first()
    if obj:
        obj.data = data.data
    else:
        obj = HomepageContentBlock(key=key, data=data.data)
        db.add(obj)
    db.commit()
    db.refresh(obj)
    return _s_content_block(obj, key)


def get_sitemap_xml(db) -> str:
    entries = db.query(SitemapEntry).filter(SitemapEntry.is_active == True).all()
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for e in entries:
        lm = e.last_modified.strftime("%Y-%m-%d") if e.last_modified else ""
        lines.append(f"  <url><loc>{e.url}</loc><changefreq>{e.change_frequency}</changefreq><priority>{e.priority}</priority>{'<lastmod>' + lm + '</lastmod>' if lm else ''}</url>")
    lines.append("</urlset>")
    return "\n".join(lines)
