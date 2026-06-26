"""
Authenticated private document download endpoint.

Documents uploaded to /private-documents/ are not reachable via the public
/storage static-files mount.  This router streams them only to authenticated
users who own the document or hold an admin/supplier-view permission.
"""
import mimetypes

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import get_private_docs_root
from app.database import get_db
from app.modules.common.auth import get_current_user, get_user_role_ids, expand_permission_slugs
from app.modules.permissions.models import Permission, RolePermission
from app.modules.users.models import User

router = APIRouter(prefix="/private-documents", tags=["Private Documents"])

_PRIVATE_PREFIX = "/private-documents/"


def _resolve_path(file_path: str):
    """Convert a /private-documents/... DB path to an absolute filesystem path."""
    # Strip the /private-documents/ prefix, then resolve under private_docs_root
    relative = file_path.removeprefix("/private-documents/")
    return get_private_docs_root() / relative


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
    from app.modules.suppliers.models import Supplier, SupplierDocument

    doc = db.query(SupplierDocument).filter(SupplierDocument.id == doc_id).first()
    if not doc or not doc.file_path:
        raise HTTPException(status_code=404, detail="Document not found")

    supplier = db.query(Supplier).filter(Supplier.id == doc.supplier_id).first()
    is_owner = supplier and supplier.user_id == current_user.id
    if not is_owner and not _has_admin_permission(db, current_user, "suppliers.view_documents", "suppliers.view", "view-suppliers"):
        raise HTTPException(status_code=403, detail="Permission denied")

    if not doc.file_path.startswith(_PRIVATE_PREFIX):
        raise HTTPException(status_code=404, detail="Document not available via this endpoint")

    abs_path = _resolve_path(doc.file_path)
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    media_type = doc.mime_type or mimetypes.guess_type(str(abs_path))[0] or "application/octet-stream"
    return FileResponse(str(abs_path), media_type=media_type, filename=doc.document_name or abs_path.name)


@router.get("/agent/{doc_id}")
def get_agent_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.modules.agents.models import Agent, AgentDocument

    doc = db.query(AgentDocument).filter(AgentDocument.id == doc_id).first()
    if not doc or not doc.file_path:
        raise HTTPException(status_code=404, detail="Document not found")

    agent = db.query(Agent).filter(Agent.id == doc.agent_id).first()
    is_owner = agent and agent.user_id == current_user.id
    if not is_owner and not _has_admin_permission(db, current_user, "agents.view_documents", "agents.view", "view-agents"):
        raise HTTPException(status_code=403, detail="Permission denied")

    if not doc.file_path.startswith(_PRIVATE_PREFIX):
        raise HTTPException(status_code=404, detail="Document not available via this endpoint")

    abs_path = _resolve_path(doc.file_path)
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    media_type = doc.mime_type or mimetypes.guess_type(str(abs_path))[0] or "application/octet-stream"
    return FileResponse(str(abs_path), media_type=media_type, filename=doc.document_name or abs_path.name)
