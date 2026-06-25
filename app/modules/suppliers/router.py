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
from app.modules.suppliers.schemas import SupplierCreate, SupplierMarkupRequest, SupplierUpdate
from app.modules.suppliers.service import (
    approve_supplier,
    create_supplier,
    get_supplier,
    list_suppliers,
    partial_approve_supplier,
    reject_supplier,
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
def suppliers(params: dict = Depends(pagination_params), country_id: str = Query(default=""), status: str = Query(default=""), approval_status: str = Query(default=""), start_date: str = Query(default=""), end_date: str = Query(default=""), db: Session = Depends(get_db), _=Depends(require_any_permission("suppliers.view", "view-suppliers"))):
    return {"status": "success", **list_suppliers(db, params["page"], params["limit"], params["search"], country_id, status, approval_status, start_date, end_date)}


@router.post("/")
def add_supplier(data: SupplierCreate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("suppliers.create", "create-suppliers"))):
    return {"status": "success", "message": "Supplier created successfully", "data": create_supplier(db, data, current_user, request)}


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

    import imghdr
    from uuid import uuid4
    from app.config import get_storage_root
    from app.modules.suppliers.models import SupplierDocument
    from app.modules.suppliers.service import _document

    storage_root = get_storage_root()
    doc_dir = storage_root / "uploads" / "supplier-documents"
    doc_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{uuid4().hex}.{extension}"
    file_path = doc_dir / filename
    file_path.write_bytes(content)

    relative_path = f"/storage/uploads/supplier-documents/{filename}"

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
