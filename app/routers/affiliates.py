from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.affiliates import Affiliate
from app.schemas.affiliates import (
    AffiliateApiLinkRequest,
    AffiliateCreate,
    AffiliateDocumentReviewRequest,
    AffiliateSelfUpdate,
    AffiliateSuspendRequest,
    AffiliateUpdate,
)
from app.services.affiliates import (
    AFFILIATE_DOCUMENT_TYPES,
    accept_affiliate_commission,
    activate_affiliate,
    approve_affiliate,
    create_affiliate,
    get_affiliate,
    list_affiliates,
    reject_affiliate,
    review_affiliate_document,
    serialize_affiliate,
    submit_affiliate_verification,
    suspend_affiliate,
    update_affiliate,
    update_affiliate_api_link,
)
from app.auth.permissions import get_current_user, get_user_role_ids, expand_permission_slugs, require_any_permission
from app.utils.pagination import pagination_params
from app.utils.operations import RejectRequest
from app.utils.ratelimit import check_rate_limit
from app.models.permissions import Permission, RolePermission
from app.models.users import User

router = APIRouter(prefix="/affiliates", tags=["Affiliates"])


@router.get("/me")
def my_affiliate(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    affiliate = db.query(Affiliate).filter(Affiliate.user_id == current_user.id).first()
    if not affiliate:
        raise HTTPException(status_code=404, detail="Affiliate profile not found")
    return {"status": "success", "data": serialize_affiliate(affiliate)}


@router.post("/me/accept-commission")
def accept_my_commission(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    affiliate = db.query(Affiliate).filter(Affiliate.user_id == current_user.id).first()
    if not affiliate:
        raise HTTPException(status_code=404, detail="Affiliate profile not found")
    return {"status": "success", "data": accept_affiliate_commission(db, affiliate.id, current_user, request)}


@router.patch("/me")
@router.put("/me")
def edit_my_affiliate(data: AffiliateSelfUpdate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    affiliate = db.query(Affiliate).filter(Affiliate.user_id == current_user.id).first()
    if not affiliate:
        raise HTTPException(status_code=404, detail="Affiliate profile not found")
    # Re-wrapped through AffiliateUpdate (the full schema) so a self-update
    # can never smuggle in status/admin_comments/commission_percentage even
    # if AffiliateSelfUpdate's field set were ever loosened later - same
    # belt-and-braces pattern as routers.suppliers.edit_my_supplier.
    safe_update = AffiliateUpdate(**data.model_dump(exclude_unset=True))
    return {"status": "success", "message": "Affiliate updated successfully", "data": update_affiliate(db, affiliate.id, safe_update, current_user, request)}


@router.get("/document-requirements")
def affiliate_document_requirements(_current_user: User = Depends(get_current_user)):
    return {
        "status": "success",
        "data": [
            {"document_type": key, **metadata}
            for key, metadata in AFFILIATE_DOCUMENT_TYPES.items()
        ],
    }


@router.post("/submit-verification")
def submit_my_verification(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return {"status": "success", "message": "Affiliate verification submitted", "data": submit_affiliate_verification(db, current_user, request)}


@router.get("")
@router.get("/")
def affiliates(
    params: dict = Depends(pagination_params),
    country_id: str = Query(default=""),
    status: str = Query(default=""),
    approval_status: str = Query(default=""),
    db: Session = Depends(get_db),
    _=Depends(require_any_permission("affiliates.view")),
):
    return {"status": "success", **list_affiliates(db, params["page"], params["limit"], params["search"], country_id, status, approval_status)}


@router.post("")
@router.post("/")
def add_affiliate(data: AffiliateCreate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("affiliates.create", "affiliates.approve"))):
    return {"status": "success", "message": "Affiliate created successfully", "data": create_affiliate(db, data, current_user, request)}


@router.get("/{affiliate_id}")
def affiliate_detail(affiliate_id: int, db: Session = Depends(get_db), _=Depends(require_any_permission("affiliates.view"))):
    return {"status": "success", "data": serialize_affiliate(get_affiliate(db, affiliate_id))}


@router.put("/{affiliate_id}")
def edit_affiliate(affiliate_id: int, data: AffiliateUpdate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("affiliates.approve"))):
    return {"status": "success", "message": "Affiliate updated successfully", "data": update_affiliate(db, affiliate_id, data, current_user, request)}


@router.get("/{affiliate_id}/commission-calculator")
def affiliate_commission_calculator(
    affiliate_id: int,
    amount: float = Query(ge=0),
    tour_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    _=Depends(require_any_permission("affiliates.view")),
):
    """Read-only preview of what Tourvaa would pay this affiliate on a
    booking of the given amount, using the same rule-resolution hierarchy
    (link -> affiliate+tour -> affiliate -> tour -> category -> global
    default) as a real conversion - see
    services.affiliate_commission.resolve_affiliate_commission_rule. Does
    not account for a link-level override, since this preview has no
    specific link."""
    from app.utils.money import money
    from app.models.cms import Tour
    from app.services.affiliate_commission import resolve_affiliate_commission_rule

    affiliate = get_affiliate(db, affiliate_id)
    eligible_amount = money(amount)
    tour = db.query(Tour).filter(Tour.id == tour_id).first() if tour_id else None
    rule = resolve_affiliate_commission_rule(
        db,
        affiliate_id=affiliate.id,
        tour_id=tour_id,
        category_id=tour.category_id if tour else None,
    )
    if rule:
        commission_type = rule.commission_type
        percentage = money(rule.percentage or 0)
        fixed_amount = money(rule.fixed_amount or 0)
    else:
        commission_type = "percentage"
        percentage = money(affiliate.commission_percentage or 0)
        fixed_amount = money(0)
    commission_amount = fixed_amount if commission_type == "fixed" else money(eligible_amount * percentage / money(100))
    return {
        "status": "success",
        "data": {
            "gross_amount": str(eligible_amount),
            "commission_type": commission_type,
            "commission_percentage": str(percentage) if commission_type == "percentage" else None,
            "commission_amount": str(commission_amount),
            "matched_rule_id": rule.id if rule else None,
        },
    }


@router.get("/{affiliate_id}/documents")
def get_affiliate_documents(affiliate_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    affiliate = get_affiliate(db, affiliate_id)
    if affiliate.user_id != current_user.id:
        role_ids = get_user_role_ids(current_user)
        allowed_slugs = expand_permission_slugs(("affiliates.view_documents", "affiliates.view"))
        allowed = (
            db.query(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .filter(RolePermission.role_id.in_(role_ids))
            .filter(Permission.slug.in_(allowed_slugs))
            .filter(Permission.is_active == True)
            .first()
        )
        if not allowed:
            raise HTTPException(status_code=403, detail="Permission denied")

    from app.models.affiliates import AffiliateDocument
    from app.services.affiliates import _document
    docs = db.query(AffiliateDocument).filter(AffiliateDocument.affiliate_id == affiliate_id).all()
    return {"status": "success", "data": [_document(doc) for doc in docs]}


@router.post("/{affiliate_id}/documents")
async def upload_affiliate_document(
    affiliate_id: int,
    request: Request,
    file: UploadFile = File(...),
    document_type: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    check_rate_limit(request, "upload", max_calls=20, window_seconds=60)
    affiliate = get_affiliate(db, affiliate_id)
    is_self_service = affiliate.user_id == current_user.id
    if not is_self_service:
        role_ids = get_user_role_ids(current_user)
        allowed_slugs = expand_permission_slugs(("affiliates.approve",))
        allowed = (
            db.query(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .filter(RolePermission.role_id.in_(role_ids))
            .filter(Permission.slug.in_(allowed_slugs))
            .filter(Permission.is_active == True)
            .first()
        )
        if not allowed:
            raise HTTPException(status_code=403, detail="Permission denied")
    # Self-service uploads must accept the commission-consent popup first
    # (CommissionConsentModal); staff/admin uploading on the affiliate's
    # behalf are never gated by it. Same rule as suppliers.
    elif affiliate.commission_accepted_at is None:
        raise HTTPException(status_code=403, detail="Please accept the Tourvaa commission rate before uploading documents.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="File is required")

    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File must be 10MB or smaller")

    allowed_types = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "image/avif": "avif",
        "application/pdf": "pdf",
        "application/msword": "doc",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    }
    extension = allowed_types.get(file.content_type or "")
    if not extension:
        filename_lower = file.filename.lower()
        if filename_lower.endswith(".pdf"):
            extension = "pdf"
        elif filename_lower.endswith(".jpg") or filename_lower.endswith(".jpeg"):
            extension = "jpg"
        elif filename_lower.endswith(".png"):
            extension = "png"
        elif filename_lower.endswith(".webp"):
            extension = "webp"
        elif filename_lower.endswith(".avif"):
            extension = "avif"
        elif filename_lower.endswith(".doc"):
            extension = "doc"
        elif filename_lower.endswith(".docx"):
            extension = "docx"
        else:
            raise HTTPException(status_code=400, detail="Only JPG, PNG, WEBP, AVIF, PDF, DOC, and DOCX files are allowed")

    # Verify the file's actual signature matches the claimed extension --
    # an extension/content-type alone can be spoofed.
    from app.utils.media import detect_image_type
    image_ext_by_signature = {"jpeg": "jpg", "png": "png", "webp": "webp", "avif": "avif"}
    if extension in image_ext_by_signature.values():
        if image_ext_by_signature.get(detect_image_type(content) or "") != extension:
            raise HTTPException(status_code=400, detail="Invalid image file")
    elif extension == "pdf" and not content.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Invalid PDF file")

    from app.utils.cloudinary_client import upload_to_cloudinary
    from app.utils.media import sanitize_filename
    from app.models.affiliates import AffiliateDocument
    from app.services.affiliates import _document

    filename = sanitize_filename(file.filename, extension)
    uploaded = upload_to_cloudinary(content, filename, folder="tourvaa/affiliate-documents", is_private=True, content_type=file.content_type)
    relative_path = f"cloudinary:{uploaded['resource_type']}:{uploaded['public_id']}"

    existing_doc = db.query(AffiliateDocument).filter(
        AffiliateDocument.affiliate_id == affiliate_id,
        AffiliateDocument.document_type == document_type
    ).first()

    if existing_doc:
        existing_doc.file_path = relative_path
        existing_doc.document_name = file.filename
        existing_doc.file_size = len(content)
        existing_doc.mime_type = file.content_type or "application/octet-stream"
        existing_doc.status = "pending"
        existing_doc.rejection_reason = None
        db.commit()
        db.refresh(existing_doc)
        doc_obj = existing_doc
    else:
        new_doc = AffiliateDocument(
            affiliate_id=affiliate_id,
            document_type=document_type,
            document_name=file.filename,
            file_path=relative_path,
            file_size=len(content),
            mime_type=file.content_type or "application/octet-stream",
            status="pending",
        )
        db.add(new_doc)
        db.commit()
        db.refresh(new_doc)
        doc_obj = new_doc

    return {
        "status": "success",
        "message": "Document uploaded successfully",
        "data": _document(doc_obj)
    }


@router.patch("/{affiliate_id}/documents/{document_id}/review")
def review_document(
    affiliate_id: int,
    document_id: int,
    data: AffiliateDocumentReviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("affiliates.approve")),
):
    return {
        "status": "success",
        "message": f"Document {data.status} successfully",
        "data": review_affiliate_document(db, document_id, data, current_user, request),
    }


@router.patch("/{affiliate_id}/approve")
def approve(affiliate_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("affiliates.approve"))):
    return {"status": "success", "message": "Affiliate approved successfully", "data": approve_affiliate(db, affiliate_id, current_user, request)}


@router.patch("/{affiliate_id}/reject")
def reject(affiliate_id: int, data: RejectRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("affiliates.reject"))):
    return {"status": "success", "message": "Affiliate rejected successfully", "data": reject_affiliate(db, affiliate_id, data, current_user, request)}


@router.post("/{affiliate_id}/activate")
def activate(affiliate_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("affiliates.activate"))):
    return {"status": "success", "message": "Affiliate activated successfully", "data": activate_affiliate(db, affiliate_id, current_user, request)}


@router.post("/{affiliate_id}/suspend")
def suspend(affiliate_id: int, data: AffiliateSuspendRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("affiliates.suspend"))):
    return {"status": "success", "message": "Affiliate suspended successfully", "data": suspend_affiliate(db, affiliate_id, data, current_user, request)}


@router.patch("/{affiliate_id}/api-link")
def api_link(affiliate_id: int, data: AffiliateApiLinkRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("affiliates.manage_api_link"))):
    return {"status": "success", "message": "Affiliate API link updated successfully", "data": update_affiliate_api_link(db, affiliate_id, data, current_user, request)}
