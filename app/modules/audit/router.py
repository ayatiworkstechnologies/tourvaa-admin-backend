from math import ceil
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.audit.models import AuditLog
from app.modules.common.auth import require_any_permission
from app.modules.common.pagination import pagination_params

router = APIRouter(prefix="/activity-logs", tags=["Activity Logs"])
alias_router = APIRouter(prefix="/audit-logs", tags=["Activity Logs"])


def serialize_log(row: AuditLog) -> dict:
    return {"id": row.id, "actor_user_id": row.actor_user_id, "action": row.action, "entity_type": row.entity_type, "entity_id": row.entity_id, "old_values": row.old_values, "new_values": row.new_values, "ip_address": row.ip_address, "user_agent": row.user_agent, "created_at": row.created_at}

@router.get("")
@router.get("/")
def activity_logs(params: dict = Depends(pagination_params), entity_type: str = Query(default=""), action: str = Query(default=""), db: Session = Depends(get_db), _=Depends(require_any_permission("activity_logs.view"))):
    query = db.query(AuditLog)
    if entity_type: query = query.filter(AuditLog.entity_type == entity_type)
    if action: query = query.filter(AuditLog.action == action)
    query = query.order_by(AuditLog.id.desc())
    total = query.count(); items = [serialize_log(row) for row in query.offset((params["page"] - 1) * params["limit"]).limit(params["limit"]).all()]
    return {"status": "success", "items": items, "data": items, "total": total, "page": params["page"], "limit": params["limit"], "total_pages": max(1, ceil(total / params["limit"]))}

@router.get("/export")
def export_logs(db: Session = Depends(get_db), _=Depends(require_any_permission("activity_logs.export", "activity_logs.view"))):
    return {"status": "success", "data": [serialize_log(row) for row in db.query(AuditLog).order_by(AuditLog.id.desc()).limit(500).all()]}


alias_router.add_api_route("", activity_logs, methods=["GET"])
alias_router.add_api_route("/", activity_logs, methods=["GET"])
alias_router.add_api_route("/export", export_logs, methods=["GET"])
