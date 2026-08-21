from math import ceil

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.services.audit import log_audit
from app.models.cms import Tour
from app.utils.money import utcnow
from app.services.notifications import enqueue_notification, notify_admins
from app.models.tour_versions import TourReviewComment, TourVersion
from app.schemas.tour_versions import ReviewCommentCreate, TourVersionReject
from app.models.users import User

# Tour.status a tour must already be in before an edit is allowed to leave it
# untouched (see _stage_pending_version) -- once a tour has been published,
# it must stay visibly live/bookable through the whole review cycle instead
# of disappearing the instant someone edits it.
LIVE_TOUR_STATUS = "published"

# Positive allow-list of tour statuses a submit-for-approval call may start
# from, named/structured the same way BOOKING_STATUS_TRANSITIONS is in
# bookings.py - a tour only has one real transition point today (submit),
# so this is a flat set rather than a full from-status -> allowed-next-statuses
# graph, but the intent (explicit allow-list, not an implicit block-list) matches.
TOUR_SUBMITTABLE_STATUSES = {"draft", "rejected"}


def _serialize(v: TourVersion) -> dict:
    return {
        "id": v.id,
        "tour_id": v.tour_id,
        "version_number": v.version_number,
        "snapshot": v.snapshot,
        "status": v.status,
        "change_kind": v.change_kind,
        "submitted_by": v.submitted_by,
        "submitter_name": v.submitter.name if v.submitter else None,
        "reviewed_by": v.reviewed_by,
        "reviewer_name": v.reviewer.name if v.reviewer else None,
        "rejection_reason": v.rejection_reason,
        "submitted_at": v.submitted_at,
        "reviewed_at": v.reviewed_at,
        "created_at": v.created_at,
    }


def _tour_snapshot(db: Session, tour: Tour) -> dict:
    from app.services.tours import (
        list_calendar,
        list_discounts,
        list_extensions,
        list_gallery,
        list_inclusions,
        list_itineraries,
        list_pricing,
    )
    snapshot = {
        "title": tour.title,
        "slug": tour.slug,
        "subtitle": tour.subtitle,
        "price_start_per_person": float(tour.price_start_per_person or 0),
        "currency": tour.currency,
        "country_id": tour.country_id,
        "country_name": tour.country.country_name if tour.country else "",
        "city_id": tour.city_id,
        "city_name": tour.city.city_name if tour.city else "",
        "category_id": tour.category_id,
        "category_name": tour.category.category_name if tour.category else "",
        "start_location": tour.start_location,
        "finish_location": tour.finish_location,
        "number_of_days": tour.number_of_days,
        "number_of_hours": tour.number_of_hours,
        "short_description": tour.short_description,
        "long_description": tour.long_description,
        "seo_title": tour.seo_title,
        "seo_description": tour.seo_description,
        "banner_image": tour.banner_image,
        "map_image": tour.map_image,
        "status": tour.status,
        # Versioned child resources -- captured so the snapshot is a true
        # record of what was actually reviewed/approved, and so live edits
        # to these can be detected and pulled back into review (see
        # maybe_resubmit_for_review below).
        "itinerary": list_itineraries(db, tour.id),
        "inclusions": list_inclusions(db, tour.id),
        "gallery": list_gallery(db, tour.id),
        "pricing": list_pricing(db, tour.id),
        "calendar": list_calendar(db, tour.id),
        "discounts": list_discounts(db, tour.id),
        "extensions": list_extensions(db, tour.id),
    }
    # The child-list serializers above return raw datetime/date/Decimal
    # values straight from the ORM; jsonable_encoder converts everything to
    # JSON-safe primitives before this dict is written to the JSON column
    # (a plain json.dumps() there would otherwise crash on datetime).
    return jsonable_encoder(snapshot)


def _stage_pending_version(db: Session, tour: Tour, actor: User, resulting_status: str = "pending_approval") -> TourVersion:
    """Adds a new pending TourVersion to the session (no commit). Shared by
    explicit submission and the auto-resubmit path triggered by editing a
    live tour.

    Once a tour has been published it must stay visibly live/bookable for
    the whole review cycle (public.py's storefront queries only ever show
    Tour.status == "published"), so Tour.status is left untouched in that
    case -- the version's own `change_kind` records what the pending review
    actually is ("pending_approval" for ordinary content edits,
    "repricing_required" for a live Supplier Pricing change) for the editor
    UI to surface instead."""
    existing_count = db.query(TourVersion).filter(TourVersion.tour_id == tour.id).count()

    # Cancel any still-pending version for this tour
    db.query(TourVersion).filter(
        TourVersion.tour_id == tour.id,
        TourVersion.status == "pending_approval",
    ).update({"status": "superseded"})

    version = TourVersion(
        tour_id=tour.id,
        version_number=existing_count + 1,
        snapshot=_tour_snapshot(db, tour),
        status="pending_approval",
        change_kind=resulting_status,
        submitted_by=actor.id,
        submitted_at=utcnow(),
    )
    db.add(version)
    if tour.status != LIVE_TOUR_STATUS:
        tour.status = resulting_status
    return version


def submit_for_approval(db: Session, tour_id: int, actor: User, request=None) -> dict:
    tour = db.query(Tour).filter(Tour.id == tour_id).first()
    if not tour:
        raise HTTPException(status_code=404, detail="Tour not found")
    if tour.status not in TOUR_SUBMITTABLE_STATUSES:
        raise HTTPException(status_code=400, detail=f"Tour must be in draft or rejected status to submit for approval (current: '{tour.status}')")

    version = _stage_pending_version(db, tour, actor)
    db.commit()
    db.refresh(version)

    notify_admins(db, notification_type="tour_submitted", title="Tour Submitted for Approval", message=f"Tour '{tour.title}' (v{version.version_number}) submitted for review.", entity_type="tour_version", entity_id=version.id)
    db.commit()

    log_audit(db, actor=actor, action="submit_for_approval", entity_type="tour_version", entity_id=version.id, old_values={}, new_values={"tour_id": tour_id, "version": version.version_number}, request=request)
    return _serialize(version)


def create_pending_version(db: Session, tour: Tour, actor: User, reason: str | None = None, resulting_status: str = "pending_approval") -> TourVersion:
    """Used when a supplier edits a versioned child resource (or the tour
    itself) while it's already active/published -- auto re-submits for
    admin review instead of letting the change go live silently."""
    version = _stage_pending_version(db, tour, actor, resulting_status)
    db.commit()
    db.refresh(version)

    message = f"Tour '{tour.title}' was edited while live and requires re-approval."
    if reason:
        message += f" ({reason})"
    notify_admins(db, notification_type="tour_resubmitted", title="Tour Resubmitted for Review", message=message, entity_type="tour_version", entity_id=version.id)
    db.commit()

    log_audit(db, actor=actor, action="auto_resubmit_for_approval", entity_type="tour_version", entity_id=version.id, old_values={}, new_values={"tour_id": tour.id, "version": version.version_number, "reason": reason})
    return version


def maybe_resubmit_for_review(db: Session, tour_id: int, actor: User) -> None:
    """If this tour is already active/published, a supplier's edit to it
    must not go live silently -- pull it back into the approval queue with
    a fresh snapshot. No-op for admin-initiated edits (admins retain direct
    authority) and for tours not yet active/published (drafts are covered
    by the normal explicit submit-for-approval flow)."""
    from app.services.supplier_scope import is_supplier_user
    if not is_supplier_user(actor):
        return
    tour = db.query(Tour).filter(Tour.id == tour_id).first()
    if not tour or tour.status not in ("active", "published"):
        return
    create_pending_version(db, tour, actor, reason="Tour content edited while live")


def mark_repricing_required(db: Session, tour_id: int, actor: User) -> None:
    """A supplier's Supplier Pricing change on a tour that's already gone
    through at least one approval must not silently change what customers
    are charged -- flag it distinctly from ordinary content edits so the
    editor can show "Repricing Required" and the storefront price stays
    frozen (see services/tours.py's _apply_pricing_computation) until an
    admin recalculates and approves it. No-op for admin edits (admins set
    Tourvaa's own pricing directly) and for tours that haven't been
    approved yet (a still-draft/rejected/first-time-pending tour has no
    live public price to protect -- its pricing follows the normal
    maybe_resubmit_for_review path instead)."""
    from app.services.supplier_scope import is_supplier_user
    if not is_supplier_user(actor):
        return
    tour = db.query(Tour).filter(Tour.id == tour_id).first()
    if not tour or tour.status not in ("active", "published", "repricing_required"):
        return
    create_pending_version(db, tour, actor, reason="Supplier pricing changed while tour is live", resulting_status="repricing_required")


def list_pending(db: Session, page: int = 1, limit: int = 20) -> dict:
    q = db.query(TourVersion).filter(TourVersion.status == "pending_approval").order_by(TourVersion.id.desc())
    total = q.count()
    items = [_serialize(v) for v in q.offset((page - 1) * limit).limit(limit).all()]
    return {"items": items, "total": total, "page": page, "limit": limit, "total_pages": max(1, ceil(total / limit))}


def list_versions(db: Session, tour_id: int, page: int = 1, limit: int = 20) -> dict:
    q = db.query(TourVersion).filter(TourVersion.tour_id == tour_id).order_by(TourVersion.version_number.desc())
    total = q.count()
    items = [_serialize(v) for v in q.offset((page - 1) * limit).limit(limit).all()]
    return {"items": items, "total": total, "page": page, "limit": limit, "total_pages": max(1, ceil(total / limit))}


def approve_version(db: Session, tour_id: int, version_id: int, actor: User, request=None) -> dict:
    version = db.query(TourVersion).filter(TourVersion.id == version_id, TourVersion.tour_id == tour_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Tour version not found")
    if version.status != "pending_approval":
        raise HTTPException(status_code=400, detail=f"Version is already '{version.status}'")

    tour = db.query(Tour).filter(Tour.id == tour_id).first()

    # Apply snapshot fields to the live tour
    snap = version.snapshot or {}
    for field in ["title", "subtitle", "currency", "country_id", "city_id", "category_id", "start_location", "finish_location", "number_of_days", "number_of_hours", "short_description", "long_description", "seo_title", "seo_description", "banner_image", "map_image"]:
        if field in snap:
            setattr(tour, field, snap[field])
    # Approval moves the tour to "active" (reviewed and correct) but not yet
    # public -- a separate admin Publish action (PATCH /tours/{id}/status)
    # makes it visible/bookable. This is intentional: it lets admins control
    # go-live timing independently of the content review. A tour that was
    # already published stays published throughout -- it was never taken
    # offline for this review (see _stage_pending_version), so approving it
    # just confirms the live edits rather than requiring a second Publish.
    if tour.status != LIVE_TOUR_STATUS:
        tour.status = "active"

    # "Admin recalculates Tourvaa Pricing" -- every pricing slab's public
    # storefront price is (re)computed from its current supplier_final_*
    # and admin_markup_* here, at the moment of approval. This is what
    # actually applies a frozen/repricing-required change (or a brand new
    # slab's first-ever price) to the live public price.
    _recalculate_storefront_prices(db, tour_id)

    version.status = "approved"
    version.reviewed_by = actor.id
    version.reviewed_at = utcnow()
    db.commit()
    db.refresh(version)

    # Notify the submitter
    if version.submitted_by:
        enqueue_notification(db, user_id=version.submitted_by, notification_type="tour_approved", title="Tour Approved", message=f"Your tour '{tour.title}' (v{version.version_number}) has been approved and is ready to publish.", entity_type="tour", entity_id=tour_id)
        db.commit()

    log_audit(db, actor=actor, action="approve_tour_version", entity_type="tour_version", entity_id=version_id, old_values={"status": "pending_approval"}, new_values={"status": "approved"}, request=request)
    return _serialize(version)


def _replace_versioned_children(db: Session, tour: Tour, snapshot: dict) -> None:
    """Deletes every current row of each versioned child collection and
    recreates it from `snapshot`, so a rejected version's live edits to
    these tables (which are written immediately on save, not staged) are
    actually rolled back rather than just flipping Tour.status. Restoring
    through each resource's own create-Payload schema reuses its field
    whitelist/validation and silently drops the snapshot's extra id/
    tour_id/timestamp keys (BaseModel's default `extra="ignore"`)."""
    from app.models.tours import (
        TourCalendar, TourDiscount, TourExtension, TourGalleryImage,
        TourInclusion, TourItinerary, TourPricing,
    )
    from app.schemas.tours import (
        CalendarPayload, DiscountPayload, ExtensionPayload,
        GalleryImagePayload, InclusionPayload, ItineraryPayload,
    )

    def _replace(model, payload_cls, items):
        db.query(model).filter(model.tour_id == tour.id).delete()
        db.flush()
        for item in items or []:
            db.add(model(tour_id=tour.id, **payload_cls(**item).model_dump()))

    _replace(TourItinerary, ItineraryPayload, snapshot.get("itinerary"))
    _replace(TourInclusion, InclusionPayload, snapshot.get("inclusions"))
    _replace(TourGalleryImage, GalleryImagePayload, snapshot.get("gallery"))
    _replace(TourExtension, ExtensionPayload, snapshot.get("extensions"))
    _replace(TourDiscount, DiscountPayload, snapshot.get("discounts"))
    _replace(TourCalendar, CalendarPayload, snapshot.get("calendar"))

    # Pricing carries server-computed markup/final/storefront columns that
    # aren't part of PricingPayload's client-settable subset -- restore the
    # full row as-is so the exact previously-approved numbers come back,
    # rather than recomputing against the supplier's *current* commission.
    db.query(TourPricing).filter(TourPricing.tour_id == tour.id).delete()
    db.flush()
    for item in snapshot.get("pricing") or []:
        row = {k: v for k, v in item.items() if k not in ("id", "tour_id", "created_at", "updated_at")}
        db.add(TourPricing(tour_id=tour.id, **row))

    from app.services.tours import recalculate_price_start
    recalculate_price_start(db, tour.id)


def _restore_snapshot(db: Session, tour: Tour, snapshot: dict) -> None:
    for field in ["title", "subtitle", "currency", "country_id", "city_id", "category_id", "start_location", "finish_location", "number_of_days", "number_of_hours", "short_description", "long_description", "seo_title", "seo_description", "banner_image", "map_image"]:
        if field in snapshot:
            setattr(tour, field, snapshot[field])
    _replace_versioned_children(db, tour, snapshot)


def _recalculate_storefront_prices(db: Session, tour_id: int) -> None:
    # Storefront price = the supplier's own price (adult_price/child_price)
    # directly - see services.tours._apply_pricing_computation for the same
    # rule applied on ordinary (non-frozen) create/update. This unfreezes
    # the storefront price a supplier's slab edit held back (spec: don't
    # let an edit silently change what's charged) once an admin has
    # reviewed and approved it.
    from app.models.tours import TourPricing
    from app.services.tours import recalculate_price_start

    for row in db.query(TourPricing).filter(TourPricing.tour_id == tour_id).all():
        row.storefront_adult_price = float(row.adult_price)
        row.storefront_child_price = float(row.child_price)
    recalculate_price_start(db, tour_id)


def reject_version(db: Session, tour_id: int, version_id: int, data: TourVersionReject, actor: User, request=None) -> dict:
    version = db.query(TourVersion).filter(TourVersion.id == version_id, TourVersion.tour_id == tour_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Tour version not found")
    if version.status != "pending_approval":
        raise HTTPException(status_code=400, detail=f"Version is already '{version.status}'")

    tour = db.query(Tour).filter(Tour.id == tour_id).first()

    # If this tour was previously approved, roll every versioned table back
    # to that last-approved snapshot instead of just flipping the status --
    # otherwise a rejected live edit (itinerary/pricing/gallery/etc, which
    # are written immediately on save) would silently remain live forever.
    # A first-ever submission with no prior approval has nothing to revert
    # to, so it falls back to the original "rejected" behavior. A published
    # tour was never taken offline for this review (see
    # _stage_pending_version), so its status is left untouched either way --
    # only the underlying data is rolled back.
    last_approved = (
        db.query(TourVersion)
        .filter(TourVersion.tour_id == tour_id, TourVersion.status == "approved")
        .order_by(TourVersion.version_number.desc())
        .first()
    )
    if last_approved:
        _restore_snapshot(db, tour, last_approved.snapshot or {})
        if tour.status != LIVE_TOUR_STATUS:
            tour.status = "active"
    elif tour.status != LIVE_TOUR_STATUS:
        tour.status = "rejected"

    version.status = "rejected"
    version.reviewed_by = actor.id
    version.reviewed_at = utcnow()
    version.rejection_reason = data.rejection_reason
    db.flush()

    for c in data.comments:
        db.add(TourReviewComment(
            tour_id=tour_id, version_id=version.id, section=c.section,
            field_name=c.field_name, comment=c.comment, severity=c.severity,
            status="open", created_by=actor.id,
        ))

    db.commit()
    db.refresh(version)

    if version.submitted_by:
        enqueue_notification(db, user_id=version.submitted_by, notification_type="tour_rejected", title="Tour Rejected", message=f"Your tour '{tour.title}' (v{version.version_number}) was rejected. Reason: {data.rejection_reason}", entity_type="tour", entity_id=tour_id)
        db.commit()

    log_audit(db, actor=actor, action="reject_tour_version", entity_type="tour_version", entity_id=version_id, old_values={"status": "pending_approval"}, new_values={"status": "rejected", "reason": data.rejection_reason}, request=request)
    return _serialize(version)


def withdraw_submission(db: Session, tour_id: int, actor: User, request=None) -> dict:
    """Lets a supplier pull back a submission that's still awaiting review,
    so they can keep editing without an admin decision landing on stale
    data. Unlike reject, nothing is reverted -- the supplier's edits are
    still exactly what they intended, they just want another pass before
    resubmitting."""
    tour = db.query(Tour).filter(Tour.id == tour_id).first()
    if not tour:
        raise HTTPException(status_code=404, detail="Tour not found")

    version = (
        db.query(TourVersion)
        .filter(TourVersion.tour_id == tour_id, TourVersion.status == "pending_approval")
        .order_by(TourVersion.version_number.desc())
        .first()
    )
    if not version:
        raise HTTPException(status_code=400, detail="There is no pending submission to withdraw")

    version.status = "withdrawn"
    version.reviewed_by = actor.id
    version.reviewed_at = utcnow()

    if tour.status != LIVE_TOUR_STATUS:
        has_prior_approval = (
            db.query(TourVersion.id)
            .filter(TourVersion.tour_id == tour_id, TourVersion.status == "approved")
            .first()
            is not None
        )
        tour.status = "active" if has_prior_approval else "draft"

    db.commit()
    db.refresh(version)

    notify_admins(db, notification_type="tour_withdrawn", title="Tour Submission Withdrawn", message=f"'{tour.title}' (v{version.version_number}) was withdrawn before review.", entity_type="tour_version", entity_id=version.id)
    db.commit()

    log_audit(db, actor=actor, action="withdraw_tour_version", entity_type="tour_version", entity_id=version.id, old_values={"status": "pending_approval"}, new_values={"status": "withdrawn", "tour_status": tour.status}, request=request)
    return _serialize(version)


def _serialize_comment(c: TourReviewComment) -> dict:
    return {
        "id": c.id,
        "tour_id": c.tour_id,
        "version_id": c.version_id,
        "section": c.section,
        "field_name": c.field_name,
        "comment": c.comment,
        "severity": c.severity,
        "status": c.status,
        "created_by": c.created_by,
        "author_name": c.author.name if c.author else None,
        "resolved_by": c.resolved_by,
        "resolver_name": c.resolver.name if c.resolver else None,
        "resolved_at": c.resolved_at,
        "created_at": c.created_at,
    }


def list_review_comments(db: Session, tour_id: int, status: str | None = None) -> list[dict]:
    q = db.query(TourReviewComment).filter(TourReviewComment.tour_id == tour_id)
    if status:
        q = q.filter(TourReviewComment.status == status)
    return [_serialize_comment(c) for c in q.order_by(TourReviewComment.created_at.desc()).all()]


def create_review_comment(db: Session, tour_id: int, data: ReviewCommentCreate, actor: User, request=None) -> dict:
    tour = db.query(Tour).filter(Tour.id == tour_id).first()
    if not tour:
        raise HTTPException(status_code=404, detail="Tour not found")
    pending_version = (
        db.query(TourVersion)
        .filter(TourVersion.tour_id == tour_id, TourVersion.status == "pending_approval")
        .order_by(TourVersion.version_number.desc())
        .first()
    )
    comment = TourReviewComment(
        tour_id=tour_id, version_id=pending_version.id if pending_version else None,
        section=data.section, field_name=data.field_name, comment=data.comment,
        severity=data.severity, status="open", created_by=actor.id,
    )
    db.add(comment)
    log_audit(db, actor=actor, action="create_review_comment", entity_type="tour", entity_id=tour_id, new_values=data.model_dump(), request=request)
    db.commit()
    db.refresh(comment)

    if tour.supplier and tour.supplier.user_id:
        enqueue_notification(db, user_id=tour.supplier.user_id, notification_type="tour_review_comment", title="New Feedback on Your Tour", message=f"An admin left {data.severity} feedback on '{tour.title}' ({data.section}).", entity_type="tour", entity_id=tour_id)
        db.commit()

    return _serialize_comment(comment)


def resolve_review_comment(db: Session, comment_id: int, actor: User, request=None) -> dict:
    comment = db.query(TourReviewComment).filter(TourReviewComment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Review comment not found")
    comment.status = "resolved"
    comment.resolved_by = actor.id
    comment.resolved_at = utcnow()
    log_audit(db, actor=actor, action="resolve_review_comment", entity_type="tour_review_comment", entity_id=comment_id, new_values={"status": "resolved"}, request=request)
    db.commit()
    db.refresh(comment)
    return _serialize_comment(comment)
