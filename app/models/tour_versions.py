from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class TourVersion(Base):
    __tablename__ = "tour_versions"

    id = Column(Integer, primary_key=True, index=True)
    tour_id = Column(Integer, ForeignKey("tours.id"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False, default=1)
    # Snapshot of all tour fields at submission time
    snapshot = Column(JSON, nullable=False)
    status = Column(String(30), default="pending_approval", nullable=False, index=True)
    # pending_approval, approved, rejected, withdrawn
    # What Tour.status would show for this review if the tour weren't
    # already published (see tour_versions.py's _stage_pending_version) --
    # "pending_approval" for ordinary content edits, "repricing_required"
    # when triggered by a live Supplier Pricing change. Kept independent of
    # Tour.status so an already-published tour can stay visibly live/public
    # for the whole review instead of disappearing the instant it's edited.
    change_kind = Column(String(30), default="pending_approval", nullable=False)
    submitted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tour = relationship("Tour")
    submitter = relationship("User", foreign_keys=[submitted_by])
    reviewer = relationship("User", foreign_keys=[reviewed_by])


class TourReviewComment(Base):
    """Section/field-level admin feedback on a tour or a specific pending
    TourVersion -- shown to the supplier inside the matching editor step
    (Changes Requested flow), separate from the single free-text
    TourVersion.rejection_reason."""
    __tablename__ = "tour_review_comments"

    id = Column(Integer, primary_key=True, index=True)
    tour_id = Column(Integer, ForeignKey("tours.id"), nullable=False, index=True)
    version_id = Column(Integer, ForeignKey("tour_versions.id"), nullable=True, index=True)
    section = Column(String(50), nullable=False)
    field_name = Column(String(100), nullable=True)
    comment = Column(Text, nullable=False)
    severity = Column(String(20), default="minor", nullable=False)
    # info, minor, required, critical
    status = Column(String(20), default="open", nullable=False, index=True)
    # open, resolved
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tour = relationship("Tour")
    version = relationship("TourVersion")
    author = relationship("User", foreign_keys=[created_by])
    resolver = relationship("User", foreign_keys=[resolved_by])
