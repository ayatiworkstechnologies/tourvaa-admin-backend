from fastapi import APIRouter, Depends, Query, Request, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.auth.schemas import RegisterSchema, VerifyEmailSchema
from app.modules.auth.service import register_user, verify_email
from app.modules.common.auth import get_current_user, require_any_permission, get_user_role_ids, expand_permission_slugs
from app.modules.common.pagination import pagination_params
from app.modules.operations import PartialApprovalRequest, RejectRequest
from app.modules.roles.models import Role
from app.modules.permissions.models import Permission, RolePermission
from app.modules.suppliers.schemas import (
    DocumentReviewRequest,
    SupplierCreate,
    SupplierMarkupRequest,
    SupplierUpdate,
    VehicleCreate,
    VehicleReviewRequest,
    VehicleUpdate,
)
from app.modules.suppliers.service import (
    approve_supplier,
    create_supplier,
    get_supplier,
    list_suppliers,
    partial_approve_supplier,
    reject_supplier,
    review_supplier_document,
    review_supplier_vehicle,
    serialize_supplier,
    submit_supplier_verification,
    update_supplier,
    update_supplier_markup,
)
from app.modules.users.models import User

router = APIRouter(prefix="/suppliers", tags=["Suppliers"])


def _registration_with_role(db: Session, data: RegisterSchema, role_slug: str):
    role = db.query(Role).filter(Role.slug == role_slug).filter(Role.is_active == True).first()
    if not role:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Registration role is not available")
    return register_user(db, data.model_copy(update={"role_id": role.id}))


@router.post("/register")
def register_supplier(data: RegisterSchema, db: Session = Depends(get_db)):
    user = _registration_with_role(db, data, "supplier")
    try:
        from app.modules.common.notification_triggers import notify_supplier_registered
        notify_supplier_registered(db, supplier_id=0, supplier_name=user.name or user.email, user_id=user.id)
        db.commit()
    except Exception:
        pass
    return {"status": "success", "message": "Supplier registration received", "data": {"id": user.id, "email": user.email, "approval_status": user.approval_status}}


@router.post("/verify-email")
def verify_supplier_email(data: VerifyEmailSchema, db: Session = Depends(get_db)):
    verify_email(db, data.token)
    return {"status": "success", "message": "Supplier email verified successfully"}


@router.post("/submit-verification")
def submit_verification(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return {"status": "success", "message": "Supplier verification submitted", "data": submit_supplier_verification(db, current_user, request)}


@router.get("/pending")
def pending_suppliers(params: dict = Depends(pagination_params), db: Session = Depends(get_db), _=Depends(require_any_permission("suppliers.view", "view-suppliers"))):
    return {"status": "success", **list_suppliers(db, params["page"], params["limit"], params["search"], approval_status="admin_review_pending")}


@router.get("")
@router.get("/")
def suppliers(
    params: dict = Depends(pagination_params),
    country_id: str = Query(default=""),
    status: str = Query(default=""),
    approval_status: str = Query(default=""),
    start_date: str = Query(default=""),
    end_date: str = Query(default=""),
    db: Session = Depends(get_db),
    _=Depends(require_any_permission("suppliers.view", "view-suppliers")),
):
    return {"status": "success", **list_suppliers(db, params["page"], params["limit"], params["search"], country_id, status, approval_status, start_date, end_date)}


@router.post("/")
def add_supplier(data: SupplierCreate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("suppliers.create", "create-suppliers"))):
    return {"status": "success", "message": "Supplier created successfully", "data": create_supplier(db, data, current_user, request)}


@router.get("/me")
def my_supplier(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.modules.suppliers.models import Supplier
    supplier = db.query(Supplier).filter(Supplier.user_id == current_user.id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier profile not found")
    return {"status": "success", "data": serialize_supplier(supplier)}


@router.patch("/me")
@router.put("/me")
def edit_my_supplier(data: SupplierUpdate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.modules.suppliers.models import Supplier
    supplier = db.query(Supplier).filter(Supplier.user_id == current_user.id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier profile not found")
    return {"status": "success", "message": "Supplier updated successfully", "data": update_supplier(db, supplier.id, data, current_user, request)}


@router.post("/me/commission-request")
def request_my_commission(data: SupplierMarkupRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.modules.suppliers.models import Supplier
    supplier = db.query(Supplier).filter(Supplier.user_id == current_user.id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier profile not found")
    supplier.markup_type = data.markup_type
    supplier.markup_value = data.markup_value
    supplier.approval_status = "admin_review_pending"
    supplier.pending_requirements = "Commission request pending admin approval"
    try:
        from app.modules.common.notification_triggers import notify_supplier_commission_requested
        notify_supplier_commission_requested(db, supplier_id=supplier.id, supplier_name=supplier.supplier_name, markup_type=data.markup_type, markup_value=data.markup_value, user_id=current_user.id)
    except Exception:
        pass
    db.commit()
    db.refresh(supplier)
    return {"status": "success", "message": "Commission request submitted", "data": serialize_supplier(supplier)}


@router.get("/me/vehicles")
def get_my_vehicles(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.modules.suppliers.models import Supplier, SupplierVehicle
    supplier = db.query(Supplier).filter(Supplier.user_id == current_user.id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier profile not found")
    vehicles = db.query(SupplierVehicle).filter(SupplierVehicle.supplier_id == supplier.id).order_by(SupplierVehicle.created_at.desc()).all()
    return {"status": "success", "data": [_serialize_vehicle(v) for v in vehicles]}


@router.post("/me/vehicles")
def add_my_vehicle(data: VehicleCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.modules.suppliers.models import Supplier, SupplierVehicle
    supplier = db.query(Supplier).filter(Supplier.user_id == current_user.id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier profile not found")
    v = SupplierVehicle(
        supplier_id=supplier.id,
        make=data.make,
        model=data.model,
        vehicle_type=data.vehicle_type,
        registration_number=data.registration_number,
        year=data.year,
        capacity=data.capacity,
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return {"status": "success", "message": "Vehicle added", "data": _serialize_vehicle(v)}


@router.patch("/me/vehicles/{vehicle_id}")
@router.put("/me/vehicles/{vehicle_id}")
def update_my_vehicle(vehicle_id: int, data: VehicleUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.modules.suppliers.models import Supplier, SupplierVehicle
    supplier = db.query(Supplier).filter(Supplier.user_id == current_user.id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier profile not found")
    v = db.query(SupplierVehicle).filter(SupplierVehicle.id == vehicle_id, SupplierVehicle.supplier_id == supplier.id).first()
    if not v:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(v, field, value)
    db.commit()
    db.refresh(v)
    return {"status": "success", "message": "Vehicle updated", "data": _serialize_vehicle(v)}


@router.delete("/me/vehicles/{vehicle_id}")
def delete_my_vehicle(vehicle_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.modules.suppliers.models import Supplier, SupplierVehicle
    supplier = db.query(Supplier).filter(Supplier.user_id == current_user.id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier profile not found")
    v = db.query(SupplierVehicle).filter(SupplierVehicle.id == vehicle_id, SupplierVehicle.supplier_id == supplier.id).first()
    if not v:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    db.delete(v)
    db.commit()
    return {"status": "success", "message": "Vehicle deleted"}


@router.post("/me/vehicles/{vehicle_id}/upload/{field}")
async def upload_vehicle_file(
    vehicle_id: int,
    field: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if field not in ("fitness_certificate", "insurance_document"):
        raise HTTPException(status_code=400, detail="field must be fitness_certificate or insurance_document")
    from app.modules.suppliers.models import Supplier, SupplierVehicle
    supplier = db.query(Supplier).filter(Supplier.user_id == current_user.id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier profile not found")
    v = db.query(SupplierVehicle).filter(SupplierVehicle.id == vehicle_id, SupplierVehicle.supplier_id == supplier.id).first()
    if not v:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    path = await _save_vehicle_file(file, "vehicle-docs")
    setattr(v, field, path)
    db.commit()
    db.refresh(v)
    return {"status": "success", "message": "File uploaded", "data": _serialize_vehicle(v)}


@router.post("/me/vehicles/{vehicle_id}/photos")
async def upload_vehicle_photos(
    vehicle_id: int,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.modules.suppliers.models import Supplier, SupplierVehicle
    supplier = db.query(Supplier).filter(Supplier.user_id == current_user.id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier profile not found")
    v = db.query(SupplierVehicle).filter(SupplierVehicle.id == vehicle_id, SupplierVehicle.supplier_id == supplier.id).first()
    if not v:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    import json
    existing: list[str] = json.loads(v.vehicle_photos) if v.vehicle_photos else []
    for f in files:
        path = await _save_vehicle_file(f, "vehicle-photos")
        if path:
            existing.append(path)
    v.vehicle_photos = json.dumps(existing)
    db.commit()
    db.refresh(v)
    return {"status": "success", "message": "Photos uploaded", "data": _serialize_vehicle(v)}


@router.delete("/me/vehicles/{vehicle_id}/photos")
def delete_vehicle_photo(vehicle_id: int, photo_url: str = Query(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.modules.suppliers.models import Supplier, SupplierVehicle
    import json
    supplier = db.query(Supplier).filter(Supplier.user_id == current_user.id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier profile not found")
    v = db.query(SupplierVehicle).filter(SupplierVehicle.id == vehicle_id, SupplierVehicle.supplier_id == supplier.id).first()
    if not v:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    photos: list[str] = json.loads(v.vehicle_photos) if v.vehicle_photos else []
    photos = [p for p in photos if p != photo_url]
    v.vehicle_photos = json.dumps(photos)
    db.commit()
    db.refresh(v)
    return {"status": "success", "message": "Photo removed", "data": _serialize_vehicle(v)}


def _serialize_vehicle(v) -> dict:
    import json
    photos_raw = v.vehicle_photos or ""
    try:
        photos = json.loads(photos_raw) if photos_raw else []
    except Exception:
        photos = [p for p in photos_raw.split(",") if p.strip()]
    return {
        "id": v.id,
        "make": v.make or "",
        "model": v.model or "",
        "vehicle_type": getattr(v, "vehicle_type", "") or "",
        "registration_number": getattr(v, "registration_number", "") or "",
        "year": v.year,
        "capacity": v.capacity,
        "fitness_certificate": v.fitness_certificate or "",
        "insurance_document": v.insurance_document or "",
        "vehicle_photos": photos,
        "approval_status": v.approval_status,
        "rejection_reason": v.rejection_reason,
        "reviewed_at": str(v.reviewed_at) if v.reviewed_at else "",
        "reviewed_by": v.reviewed_by,
        "created_at": str(v.created_at) if v.created_at else "",
    }


async def _save_vehicle_file(upload: UploadFile, subfolder: str) -> str:
    from uuid import uuid4
    from app.modules.common.imagekit_client import upload_to_imagekit
    ALLOWED = {
        "image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png",
        "image/webp": "webp", "application/pdf": "pdf",
    }
    content = await upload.read()
    if not content:
        return ""
    ext = ALLOWED.get(upload.content_type or "")
    if not ext:
        fname = (upload.filename or "").lower()
        for s, e in [(".pdf", "pdf"), (".jpg", "jpg"), (".jpeg", "jpg"), (".png", "png"), (".webp", "webp")]:
            if fname.endswith(s):
                ext = e
                break
    if not ext:
        return ""
    filename = f"{uuid4().hex}.{ext}"
    uploaded = upload_to_imagekit(content, filename, folder=f"/tourvaa/{subfolder}")
    return uploaded["url"]


@router.post("/{supplier_id}/submit-verification")
def submit_verification_by_id(supplier_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return {"status": "success", "message": "Supplier verification submitted", "data": submit_supplier_verification(db, current_user, request)}


@router.get("/{supplier_id}")
def supplier_detail(supplier_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    supplier = get_supplier(db, supplier_id)
    if supplier.user_id != current_user.id:
        role_ids = get_user_role_ids(current_user)
        allowed_slugs = expand_permission_slugs(("suppliers.view", "view-suppliers"))
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
    return {"status": "success", "data": serialize_supplier(supplier)}


@router.put("/{supplier_id}")
@router.patch("/{supplier_id}")
def edit_supplier(supplier_id: int, data: SupplierUpdate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    supplier = get_supplier(db, supplier_id)
    if supplier.user_id != current_user.id:
        role_ids = get_user_role_ids(current_user)
        allowed_slugs = expand_permission_slugs(("suppliers.edit", "update-suppliers"))
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
    return {"status": "success", "message": "Supplier updated successfully", "data": update_supplier(db, supplier_id, data, current_user, request)}


@router.get("/{supplier_id}/documents")
def get_supplier_documents(supplier_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    supplier = get_supplier(db, supplier_id)
    if supplier.user_id != current_user.id:
        role_ids = get_user_role_ids(current_user)
        allowed_slugs = expand_permission_slugs(("suppliers.view_documents", "suppliers.view"))
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
    
    from app.modules.suppliers.models import SupplierDocument
    from app.modules.suppliers.service import _document
    docs = db.query(SupplierDocument).filter(SupplierDocument.supplier_id == supplier_id).all()
    return {"status": "success", "data": [_document(doc) for doc in docs]}


@router.post("/{supplier_id}/documents")
async def upload_supplier_document(
    supplier_id: int,
    request: Request,
    file: UploadFile = File(...),
    document_type: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    supplier = get_supplier(db, supplier_id)
    if supplier.user_id != current_user.id:
        role_ids = get_user_role_ids(current_user)
        allowed_slugs = expand_permission_slugs(("suppliers.edit", "update-suppliers"))
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

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="File is required")

    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File must be 10MB or smaller")

    allowed_types = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
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
        elif filename_lower.endswith(".doc"):
            extension = "doc"
        elif filename_lower.endswith(".docx"):
            extension = "docx"
        else:
            raise HTTPException(status_code=400, detail="Only JPG, PNG, WEBP, PDF, DOC, and DOCX files are allowed")

    from uuid import uuid4
    from app.modules.common.imagekit_client import upload_to_imagekit
    from app.modules.suppliers.models import SupplierDocument
    from app.modules.suppliers.service import _document

    filename = f"{uuid4().hex}.{extension}"
    uploaded = upload_to_imagekit(content, filename, folder="/tourvaa/supplier-documents", is_private=True)
    relative_path = f"imagekit:{uploaded['file_path']}"

    existing_doc = db.query(SupplierDocument).filter(
        SupplierDocument.supplier_id == supplier_id,
        SupplierDocument.document_type == document_type
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
        new_doc = SupplierDocument(
            supplier_id=supplier_id,
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


@router.patch("/{supplier_id}/documents/{document_id}/review")
def review_document(
    supplier_id: int,
    document_id: int,
    data: DocumentReviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("suppliers.approve", "suppliers.reject")),
):
    return {
        "status": "success",
        "message": f"Document {data.status} successfully",
        "data": review_supplier_document(db, supplier_id, document_id, data, current_user, request),
    }


@router.patch("/{supplier_id}/vehicles/{vehicle_id}/review")
def review_vehicle(
    supplier_id: int,
    vehicle_id: int,
    data: VehicleReviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission("suppliers.approve", "suppliers.reject")),
):
    return {
        "status": "success",
        "message": f"Vehicle {data.approval_status} successfully",
        "data": review_supplier_vehicle(db, supplier_id, vehicle_id, data, current_user, request),
    }


@router.post("/{supplier_id}/approve")
@router.patch("/{supplier_id}/approve")
def approve(supplier_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("suppliers.approve"))):
    return {"status": "success", "message": "Supplier approved successfully", "data": approve_supplier(db, supplier_id, current_user, request)}


@router.post("/{supplier_id}/reject")
@router.patch("/{supplier_id}/reject")
def reject(supplier_id: int, data: RejectRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("suppliers.reject"))):
    return {"status": "success", "message": "Supplier rejected successfully", "data": reject_supplier(db, supplier_id, data, current_user, request)}


@router.post("/{supplier_id}/partial-approve")
@router.patch("/{supplier_id}/partial-approve")
def partial_approve(supplier_id: int, data: PartialApprovalRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("suppliers.partial_approve", "suppliers.approve"))):
    return {"status": "success", "message": "Supplier partially approved successfully", "data": partial_approve_supplier(db, supplier_id, data, current_user, request)}


@router.post("/{supplier_id}/request-reupload")
def request_reupload(supplier_id: int, data: PartialApprovalRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("suppliers.reject", "suppliers.approve"))):
    return {"status": "success", "message": "Supplier reupload requested", "data": partial_approve_supplier(db, supplier_id, data, current_user, request)}


@router.patch("/{supplier_id}/markup")
def markup(supplier_id: int, data: SupplierMarkupRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("suppliers.manage_markup"))):
    return {"status": "success", "message": "Supplier markup updated successfully", "data": update_supplier_markup(db, supplier_id, data, current_user, request)}
