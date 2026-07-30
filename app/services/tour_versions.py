from math import ceil

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.services.audit import log_audit
from app.models.cms import Tour
from app.utils.money import utcnow
from app.services.notifications import enqueue_notification, notify_admins
from app.models.tour_versions import TourVersion
from app.schemas.tour_versions import TourVersionReject
from app.models.users import User

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
    return {
        "title": tour.title,
        "slug": tour.slug,
        "subtitle": tour.subtitle,
        "price_start_per_person": float(tour.price_start_per_person or 0),
        "currency": tour.currency,
        "country_id": tour.country_id,
        "city_id": tour.city_id,
        "category_id": tour.category_id,
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


def _stage_pending_version(db: Session, tour: Tour, actor: User) -> TourVersion:
    """Adds a new pending TourVersion to the session (no commit) and flips
    the tour to pending_approval. Shared by explicit submission and the
    auto-resubmit path triggered by editing a live tour."""
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
        submitted_by=actor.id,
        submitted_at=utcnow(),
    )
    db.add(version)
    # Mark tour as pending_approval so it shows up in the queue
    tour.status = "pending_approval"
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


def create_pending_version(db: Session, tour: Tour, actor: User, reason: str | None = None) -> TourVersion:
    """Used when a supplier edits a versioned child resource (or the tour
    itself) while it's already active/published -- auto re-submits for
    admin review instead of letting the change go live silently."""
    version = _stage_pending_version(db, tour, actor)
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


def list_pending(db: Session, page: int = 1, limit: int = 20) -> dict:
    q = db.query(TourVersion).filter(TourVersion.status == "pending_approval").order_by(TourVersion.id.desc())
    total = q.count()
    items = [_serialize(v) for v in q.offset((page - 1) * limit).limit(limit).all()]
    return {"items": items, "data": items, "total": total, "page": page, "limit": limit, "total_pages": max(1, ceil(total / limit))}


def list_versions(db: Session, tour_id: int, page: int = 1, limit: int = 20) -> dict:
    q = db.query(TourVersion).filter(TourVersion.tour_id == tour_id).order_by(TourVersion.version_number.desc())
    total = q.count()
    items = [_serialize(v) for v in q.offset((page - 1) * limit).limit(limit).all()]
    return {"items": items, "data": items, "total": total, "page": page, "limit": limit, "total_pages": max(1, ceil(total / limit))}


def approve_version(db: Session, tour_id: int, version_id: int, actor: User, request=None) -> dict:
    version = db.query(TourVersion).filter(TourVersion.id == version_id, TourVersion.tour_id == tour_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Tour version not found")
    if version.status != "pending_approval":
        raise HTTPException(status_code=400, detail=f"Version is already '{version.status}'")

    tour = db.query(Tour).filter(Tour.id == tour_id).first()

    # Apply snapshot fields to the live tour
    snap = version.snapshot or {}
    for field in ["title", "subtitle", "price_start_per_person", "currency", "country_id", "city_id", "category_id", "start_location", "finish_location", "number_of_days", "number_of_hours", "short_description", "long_description", "seo_title", "seo_description", "banner_image", "map_image"]:
        if field in snap:
            setattr(tour, field, snap[field])
    # Approval moves the tour to "active" (reviewed and correct) but not yet
    # public -- a separate admin Publish action (PATCH /tours/{id}/status)
    # makes it visible/bookable. This is intentional: it lets admins control
    # go-live timing independently of the content review.
    tour.status = "active"

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


def reject_version(db: Session, tour_id: int, version_id: int, data: TourVersionReject, actor: User, request=None) -> dict:
    version = db.query(TourVersion).filter(TourVersion.id == version_id, TourVersion.tour_id == tour_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Tour version not found")
    if version.status != "pending_approval":
        raise HTTPException(status_code=400, detail=f"Version is already '{version.status}'")

    tour = db.query(Tour).filter(Tour.id == tour_id).first()
    tour.status = "rejected"

    version.status = "rejected"
    version.reviewed_by = actor.id
    version.reviewed_at = utcnow()
    version.rejection_reason = data.rejection_reason
    db.commit()
    db.refresh(version)

    if version.submitted_by:
        enqueue_notification(db, user_id=version.submitted_by, notification_type="tour_rejected", title="Tour Rejected", message=f"Your tour '{tour.title}' (v{version.version_number}) was rejected. Reason: {data.rejection_reason}", entity_type="tour", entity_id=tour_id)
        db.commit()

    log_audit(db, actor=actor, action="reject_tour_version", entity_type="tour_version", entity_id=version_id, old_values={"status": "pending_approval"}, new_values={"status": "rejected", "reason": data.rejection_reason}, request=request)
    return _serialize(version)
