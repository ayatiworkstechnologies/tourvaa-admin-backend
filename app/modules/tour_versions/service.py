from math import ceil

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.modules.audit.service import log_audit
from app.modules.cms.models import Tour
from app.modules.common.money import utcnow
from app.modules.notifications.service import enqueue_notification, notify_admins
from app.modules.tour_versions.models import TourVersion
from app.modules.tour_versions.schemas import TourVersionReject
from app.modules.users.models import User


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


def _tour_snapshot(tour: Tour) -> dict:
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
    }


def submit_for_approval(db: Session, tour_id: int, actor: User, request=None) -> dict:
    tour = db.query(Tour).filter(Tour.id == tour_id).first()
    if not tour:
        raise HTTPException(status_code=404, detail="Tour not found")

    # Count existing versions
    existing_count = db.query(TourVersion).filter(TourVersion.tour_id == tour_id).count()

    # Cancel any still-pending version for this tour
    db.query(TourVersion).filter(
        TourVersion.tour_id == tour_id,
        TourVersion.status == "pending_approval",
    ).update({"status": "superseded"})

    version = TourVersion(
        tour_id=tour_id,
        version_number=existing_count + 1,
        snapshot=_tour_snapshot(tour),
        status="pending_approval",
        submitted_by=actor.id,
        submitted_at=utcnow(),
    )
    db.add(version)
    # Mark tour as pending_approval so it shows up in the queue
    tour.status = "pending_approval"
    db.commit()
    db.refresh(version)

    notify_admins(db, notification_type="tour_submitted", title="Tour Submitted for Approval", message=f"Tour '{tour.title}' (v{version.version_number}) submitted for review.", entity_type="tour_version", entity_id=version.id)
    db.commit()

    log_audit(db, actor=actor, action="submit_for_approval", entity_type="tour_version", entity_id=version.id, old_values={}, new_values={"tour_id": tour_id, "version": version.version_number}, request=request)
    return _serialize(version)


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
    tour.status = "active"

    version.status = "approved"
    version.reviewed_by = actor.id
    version.reviewed_at = utcnow()
    db.commit()
    db.refresh(version)

    # Notify the submitter
    if version.submitted_by:
        enqueue_notification(db, user_id=version.submitted_by, notification_type="tour_approved", title="Tour Approved", message=f"Your tour '{tour.title}' (v{version.version_number}) has been approved and is now live.", entity_type="tour", entity_id=tour_id)
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
