"""
Authenticated private document download endpoint.

Documents uploaded to /private-documents/ are not reachable via the public
/storage static-files mount.  This router streams them only to authenticated
users who own the document or hold an admin/supplier-view permission.
"""
import mimetypes

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import get_private_docs_root
from app.database import get_db
from app.auth.permissions import get_current_user, get_user_role_ids, expand_permission_slugs
from app.utils.imagekit_client import get_private_file_url
from app.models.permissions import Permission, RolePermission
from app.models.users import User

router = APIRouter(prefix="/private-documents", tags=["Private Documents"])

_PRIVATE_PREFIX = "/private-documents/"
_IMAGEKIT_PREFIX = "imagekit:"


def _resolve_path(file_path: str):
    """Convert a /private-documents/... DB path to an absolute filesystem path."""
    # Strip the /private-documents/ prefix, then resolve under private_docs_root
    relative = file_path.removeprefix("/private-documents/")
    return get_private_docs_root() / relative


def _serve_document(doc):
    """Return a response for a document's file_path, whichever backend stored it."""
    if doc.file_path.startswith(_IMAGEKIT_PREFIX):
        imagekit_path = doc.file_path.removeprefix(_IMAGEKIT_PREFIX)
        return RedirectResponse(get_private_file_url(imagekit_path))

    if not doc.file_path.startswith(_PRIVATE_PREFIX):
        raise HTTPException(status_code=404, detail="Document not available via this endpoint")

    abs_path = _resolve_path(doc.file_path)
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    media_type = doc.mime_type or mimetypes.guess_type(str(abs_path))[0] or "application/octet-stream"
    return FileResponse(str(abs_path), media_type=media_type, filename=doc.document_name or abs_path.name)


def _has_admin_permission(db: Session, user: User, *slugs: str) -> bool:
    role_ids = get_user_role_ids(user)
    if not role_ids:
        return False
    allowed = expand_permission_slugs(slugs)
    return bool(
        db.query(Permission)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .filter(RolePermission.role_id.in_(role_ids))
        .filter(Permission.slug.in_(allowed))
        .filter(Permission.is_active == True)
        .first()
    )


@router.get("/supplier/{doc_id}")
def get_supplier_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.suppliers import Supplier, SupplierDocument

    doc = db.query(SupplierDocument).filter(SupplierDocument.id == doc_id).first()
    if not doc or not doc.file_path:
        raise HTTPException(status_code=404, detail="Document not found")

    supplier = db.query(Supplier).filter(Supplier.id == doc.supplier_id).first()
    is_owner = supplier and supplier.user_id == current_user.id
    if not is_owner and not _has_admin_permission(db, current_user, "suppliers.view_documents", "suppliers.view", "view-suppliers"):
        raise HTTPException(status_code=403, detail="Permission denied")

    return _serve_document(doc)


@router.get("/agent/{doc_id}")
def get_agent_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.agents import Agent, AgentDocument

    doc = db.query(AgentDocument).filter(AgentDocument.id == doc_id).first()
    if not doc or not doc.file_path:
        raise HTTPException(status_code=404, detail="Document not found")

    agent = db.query(Agent).filter(Agent.id == doc.agent_id).first()
    is_owner = agent and agent.user_id == current_user.id
    if not is_owner and not _has_admin_permission(db, current_user, "agents.view_documents", "agents.view", "view-agents"):
        raise HTTPException(status_code=403, detail="Permission denied")

    return _serve_document(doc)
