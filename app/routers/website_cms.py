from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.permissions import require_any_permission
from app.utils.pagination import pagination_params
from app.services import website_cms as service
from app.schemas.website_cms import (
    BannerPayload, BlogPayload, CmsPagePayload, ContentBlockPayload,
    ExternalLinkPayload, FavouriteCountryPayload, FooterLinkPayload,
    FooterSectionPayload, HandpickedTourPayload, HelpArticlePayload,
    PolicyPayload, PopularDestinationPayload, PopularTourPayload, PopupPayload,
    ReviewPayload, SitemapEntryPayload, TourOnDealPayload,
)

router = APIRouter(prefix="/cms", tags=["Website CMS"])

CMS_CREATE_PERMS = ("website_cms.create",)
CMS_EDIT_PERMS = ("website_cms.edit",)
CMS_DELETE_PERMS = ("website_cms.delete",)


# banners

@router.get("/homepage-banners")
def list_banners(pagination=Depends(pagination_params), active_only: bool = Query(default=False), db: Session = Depends(get_db)):
    return {"status": "success", **service.list_banners(db, pagination["page"], pagination["limit"], active_only)}

@router.post("/homepage-banners")
def create_banner(data: BannerPayload, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_CREATE_PERMS))):
    return {"status": "success", "data": service.create_banner(db, data)}

@router.put("/homepage-banners/{item_id}")
def update_banner(item_id: int, data: BannerPayload, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_EDIT_PERMS))):
    return {"status": "success", "data": service.update_banner(db, item_id, data)}

@router.delete("/homepage-banners/{item_id}")
def delete_banner(item_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_DELETE_PERMS))):
    service.delete_banner(db, item_id)
    return {"status": "success", "message": "Banner deleted"}


# popular destinations

@router.get("/popular-destinations")
def list_destinations(pagination=Depends(pagination_params), active_only: bool = Query(default=False), db: Session = Depends(get_db)):
    return {"status": "success", **service.list_destinations(db, pagination["page"], pagination["limit"], active_only)}

@router.post("/popular-destinations")
def create_destination(data: PopularDestinationPayload, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_CREATE_PERMS))):
    return {"status": "success", "data": service.create_destination(db, data)}

@router.put("/popular-destinations/{item_id}")
def update_destination(item_id: int, data: PopularDestinationPayload, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_EDIT_PERMS))):
    return {"status": "success", "data": service.update_destination(db, item_id, data)}

@router.delete("/popular-destinations/{item_id}")
def delete_destination(item_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_DELETE_PERMS))):
    service.delete_destination(db, item_id)
    return {"status": "success", "message": "Destination deleted"}


# popular tours

@router.get("/popular-tours")
def list_popular_tours(pagination=Depends(pagination_params), active_only: bool = Query(default=False), published_only: bool = Query(default=False), db: Session = Depends(get_db)):
    return {"status": "success", **service.list_popular_tours(db, pagination["page"], pagination["limit"], published_only, active_only)}

@router.post("/popular-tours")
def create_popular_tour(data: PopularTourPayload, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_CREATE_PERMS))):
    return {"status": "success", "data": service.create_popular_tour(db, data)}

@router.delete("/popular-tours/{item_id}")
def delete_popular_tour(item_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_DELETE_PERMS))):
    service.delete_popular_tour(db, item_id)
    return {"status": "success", "message": "Deleted"}


# tours on deals

@router.get("/tours-on-deals")
def list_deals(pagination=Depends(pagination_params), active_only: bool = Query(default=False), published_only: bool = Query(default=False), db: Session = Depends(get_db)):
    return {"status": "success", **service.list_deals(db, pagination["page"], pagination["limit"], active_only, published_only)}

@router.post("/tours-on-deals")
def create_deal(data: TourOnDealPayload, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_CREATE_PERMS))):
    return {"status": "success", "data": service.create_deal(db, data)}

@router.put("/tours-on-deals/{item_id}")
def update_deal(item_id: int, data: TourOnDealPayload, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_EDIT_PERMS))):
    return {"status": "success", "data": service.update_deal(db, item_id, data)}

@router.delete("/tours-on-deals/{item_id}")
def delete_deal(item_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_DELETE_PERMS))):
    service.delete_deal(db, item_id)
    return {"status": "success", "message": "Deal removed"}


# handpicked tours

@router.get("/handpicked-tours")
def list_handpicked_tours(pagination=Depends(pagination_params), active_only: bool = Query(default=False), published_only: bool = Query(default=False), db: Session = Depends(get_db)):
    return {"status": "success", **service.list_handpicked_tours(db, pagination["page"], pagination["limit"], published_only, active_only)}

@router.post("/handpicked-tours")
def create_handpicked_tour(data: HandpickedTourPayload, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_CREATE_PERMS))):
    return {"status": "success", "data": service.create_handpicked_tour(db, data)}

@router.delete("/handpicked-tours/{item_id}")
def delete_handpicked_tour(item_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_DELETE_PERMS))):
    service.delete_handpicked_tour(db, item_id)
    return {"status": "success", "message": "Deleted"}


# favourite countries

@router.get("/favourite-countries")
def list_favourite_countries(pagination=Depends(pagination_params), active_only: bool = Query(default=False), db: Session = Depends(get_db)):
    return {"status": "success", **service.list_favourite_countries(db, pagination["page"], pagination["limit"], active_only)}

@router.post("/favourite-countries")
def create_favourite_country(data: FavouriteCountryPayload, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_CREATE_PERMS))):
    return {"status": "success", "data": service.create_favourite_country(db, data)}

@router.put("/favourite-countries/{item_id}")
def update_favourite_country(item_id: int, data: FavouriteCountryPayload, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_EDIT_PERMS))):
    return {"status": "success", "data": service.update_favourite_country(db, item_id, data)}

@router.delete("/favourite-countries/{item_id}")
def delete_favourite_country(item_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_DELETE_PERMS))):
    service.delete_favourite_country(db, item_id)
    return {"status": "success", "message": "Deleted"}


# generic homepage content blocks

@router.get("/content-blocks/{key}")
def get_content_block(key: str, db: Session = Depends(get_db)):
    return {"status": "success", "data": service.get_content_block(db, key)}

@router.put("/content-blocks/{key}")
def upsert_content_block(key: str, data: ContentBlockPayload, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_EDIT_PERMS, *CMS_CREATE_PERMS))):
    return {"status": "success", "data": service.upsert_content_block(db, key, data)}


# blogs

@router.get("/blogs")
def list_blogs(pagination=Depends(pagination_params), active_only: bool = Query(default=False), slug: str = Query(default=""), db: Session = Depends(get_db)):
    return {"status": "success", **service.list_blogs(db, pagination["page"], pagination["limit"], active_only, slug)}

@router.get("/blogs/{item_id}")
def get_blog(item_id: int, db: Session = Depends(get_db)):
    return {"status": "success", "data": service.get_blog(db, item_id)}

@router.post("/blogs")
def create_blog(data: BlogPayload, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_CREATE_PERMS))):
    return {"status": "success", "data": service.create_blog(db, data)}

@router.put("/blogs/{item_id}")
def update_blog(item_id: int, data: BlogPayload, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_EDIT_PERMS))):
    return {"status": "success", "data": service.update_blog(db, item_id, data)}

@router.delete("/blogs/{item_id}")
def delete_blog(item_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_DELETE_PERMS))):
    service.delete_blog(db, item_id)
    return {"status": "success", "message": "Blog deleted"}


# cms pages

@router.get("/pages")
def list_cms_pages(pagination=Depends(pagination_params), active_only: bool = Query(default=False), db: Session = Depends(get_db)):
    return {"status": "success", **service.list_cms_pages(db, pagination["page"], pagination["limit"], active_only)}

@router.post("/pages")
def create_cms_page(data: CmsPagePayload, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_CREATE_PERMS))):
    return {"status": "success", "data": service.create_cms_page(db, data)}

@router.put("/pages/{item_id}")
def update_cms_page(item_id: int, data: CmsPagePayload, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_EDIT_PERMS))):
    return {"status": "success", "data": service.update_cms_page(db, item_id, data)}

@router.delete("/pages/{item_id}")
def delete_cms_page(item_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_DELETE_PERMS))):
    service.delete_cms_page(db, item_id)
    return {"status": "success", "message": "Page deleted"}

@router.get("/pages/by-slug/{slug}")
def public_cms_page(slug: str, db: Session = Depends(get_db)):
    """Public, no auth: a published page's content by slug - what the site's
    dynamic [slug] route fetches. A draft page 404s here."""
    return {"status": "success", "data": service.get_cms_page_by_slug(db, slug)}


# customer reviews

@router.get("/customer-reviews")
def list_reviews(pagination=Depends(pagination_params), active_only: bool = Query(default=False), db: Session = Depends(get_db)):
    return {"status": "success", **service.list_reviews(db, pagination["page"], pagination["limit"], active_only)}

@router.post("/customer-reviews")
def create_review(data: ReviewPayload, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_CREATE_PERMS))):
    return {"status": "success", "data": service.create_review(db, data)}

@router.put("/customer-reviews/{item_id}")
def update_review(item_id: int, data: ReviewPayload, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_EDIT_PERMS))):
    return {"status": "success", "data": service.update_review(db, item_id, data)}

@router.delete("/customer-reviews/{item_id}")
def delete_review(item_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_DELETE_PERMS))):
    service.delete_review(db, item_id)
    return {"status": "success", "message": "Review deleted"}


# help centre

@router.get("/help-centre")
def list_help(
    pagination=Depends(pagination_params),
    category: str = Query(default=""),
    active_only: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    return {"status": "success", **service.list_help(db, pagination["page"], pagination["limit"], category, active_only)}

@router.post("/help-centre")
def create_help(data: HelpArticlePayload, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_CREATE_PERMS))):
    return {"status": "success", "data": service.create_help(db, data)}

@router.put("/help-centre/{item_id}")
def update_help(item_id: int, data: HelpArticlePayload, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_EDIT_PERMS))):
    return {"status": "success", "data": service.update_help(db, item_id, data)}

@router.delete("/help-centre/{item_id}")
def delete_help(item_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_DELETE_PERMS))):
    service.delete_help(db, item_id)
    return {"status": "success", "message": "Article deleted"}


# policies

@router.get("/policies")
def list_policies(pagination=Depends(pagination_params), db: Session = Depends(get_db)):
    return {"status": "success", **service.list_policies(db, pagination["page"], pagination["limit"])}

@router.get("/policies/{slug}")
def get_policy(slug: str, db: Session = Depends(get_db)):
    return {"status": "success", "data": service.get_policy_by_slug(db, slug)}

@router.put("/policies")
def upsert_policy(data: PolicyPayload, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_EDIT_PERMS, *CMS_CREATE_PERMS))):
    return {"status": "success", "data": service.upsert_policy(db, data)}


# promotional popups

@router.get("/promotional-popups")
def list_popups(pagination=Depends(pagination_params), active_only: bool = Query(default=False), db: Session = Depends(get_db)):
    return {"status": "success", **service.list_popups(db, pagination["page"], pagination["limit"], active_only)}

@router.post("/promotional-popups")
def create_popup(data: PopupPayload, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_CREATE_PERMS))):
    return {"status": "success", "data": service.create_popup(db, data)}

@router.put("/promotional-popups/{item_id}")
def update_popup(item_id: int, data: PopupPayload, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_EDIT_PERMS))):
    return {"status": "success", "data": service.update_popup(db, item_id, data)}

@router.delete("/promotional-popups/{item_id}")
def delete_popup(item_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_DELETE_PERMS))):
    service.delete_popup(db, item_id)
    return {"status": "success", "message": "Popup deleted"}


# external links

@router.get("/external-links")
def list_links(pagination=Depends(pagination_params), location: str = Query(default=""), db: Session = Depends(get_db)):
    return {"status": "success", **service.list_external_links(db, pagination["page"], pagination["limit"], location)}

@router.post("/external-links")
def create_link(data: ExternalLinkPayload, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_CREATE_PERMS))):
    return {"status": "success", "data": service.create_external_link(db, data)}

@router.put("/external-links/{item_id}")
def update_link(item_id: int, data: ExternalLinkPayload, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_EDIT_PERMS))):
    return {"status": "success", "data": service.update_external_link(db, item_id, data)}

@router.delete("/external-links/{item_id}")
def delete_link(item_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_DELETE_PERMS))):
    service.delete_external_link(db, item_id)
    return {"status": "success", "message": "Link deleted"}


# footer sections & links

@router.get("/footer")
def public_footer(db: Session = Depends(get_db)):
    """Public, no-auth: the site footer's active sections + active links, in
    display order. This is what PublicFooter.tsx fetches on every render."""
    return {"status": "success", "data": service.get_public_footer(db)}

@router.get("/footer-sections")
def list_footer_sections(pagination=Depends(pagination_params), db: Session = Depends(get_db)):
    return {"status": "success", **service.list_footer_sections(db, pagination["page"], pagination["limit"])}

@router.post("/footer-sections")
def create_footer_section(data: FooterSectionPayload, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_CREATE_PERMS))):
    return {"status": "success", "data": service.create_footer_section(db, data)}

@router.put("/footer-sections/{item_id}")
def update_footer_section(item_id: int, data: FooterSectionPayload, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_EDIT_PERMS))):
    return {"status": "success", "data": service.update_footer_section(db, item_id, data)}

@router.delete("/footer-sections/{item_id}")
def delete_footer_section(item_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_DELETE_PERMS))):
    service.delete_footer_section(db, item_id)
    return {"status": "success", "message": "Footer section deleted"}

@router.get("/footer-links")
def list_footer_links(pagination=Depends(pagination_params), section_id: int | None = Query(default=None), db: Session = Depends(get_db)):
    return {"status": "success", **service.list_footer_links(db, pagination["page"], pagination["limit"], section_id)}

@router.post("/footer-links")
def create_footer_link(data: FooterLinkPayload, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_CREATE_PERMS))):
    return {"status": "success", "data": service.create_footer_link(db, data)}

@router.put("/footer-links/{item_id}")
def update_footer_link(item_id: int, data: FooterLinkPayload, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_EDIT_PERMS))):
    return {"status": "success", "data": service.update_footer_link(db, item_id, data)}

@router.delete("/footer-links/{item_id}")
def delete_footer_link(item_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_DELETE_PERMS))):
    service.delete_footer_link(db, item_id)
    return {"status": "success", "message": "Footer link deleted"}


# sitemap

@router.get("/sitemap")
def list_sitemap_entries(pagination=Depends(pagination_params), db: Session = Depends(get_db)):
    return {"status": "success", **service.list_sitemap(db, pagination["page"], pagination["limit"])}

@router.get("/sitemap.xml", response_class=Response)
def get_sitemap_xml(db: Session = Depends(get_db)):
    content = service.get_sitemap_xml(db)
    return Response(content=content, media_type="application/xml")

@router.post("/sitemap")
def create_sitemap_entry(data: SitemapEntryPayload, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_CREATE_PERMS))):
    return {"status": "success", "data": service.create_sitemap_entry(db, data)}

@router.put("/sitemap/{item_id}")
def update_sitemap_entry(item_id: int, data: SitemapEntryPayload, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_EDIT_PERMS))):
    return {"status": "success", "data": service.update_sitemap_entry(db, item_id, data)}

@router.delete("/sitemap/{item_id}")
def delete_sitemap_entry(item_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission(*CMS_DELETE_PERMS))):
    service.delete_sitemap_entry(db, item_id)
    return {"status": "success", "message": "Entry deleted"}
