import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.permissions import ACCESS_COOKIE_NAME, _decode_token, require_any_permission
from app.models.customers import Customer
from app.utils.pagination import pagination_params
from app.utils.ratelimit import check_rate_limit
from app.schemas.chatbot import (
    ChatFeedbackCreate,
    ChatFeedbackResponse,
    ChatMessageRequest,
    FAQCreate,
    FAQResponse,
    FAQUpdate,
)
from app.services import chatbot as service
from app.services import rag

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chatbot", tags=["Chatbot"])


def _resolve_customer_id(request: Request, db: Session) -> int | None:
    """Best-effort caller identification for /chat. Never raises -- an
    anonymous visitor and a logged-in customer hit the same public endpoint;
    only the latter gets booking-aware answers."""
    token = None
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    if not token:
        token = request.cookies.get(ACCESS_COOKIE_NAME, "")
    if not token:
        return None
    try:
        payload = _decode_token(token)
    except HTTPException:
        return None
    user_id = payload.get("user_id")
    if not user_id:
        return None
    customer = db.query(Customer).filter(Customer.user_id == user_id).first()
    return customer.id if customer else None


@router.post("/chat")
def chat(payload: ChatMessageRequest, request: Request, db: Session = Depends(get_db)):
    check_rate_limit(request, "chatbot-chat", max_calls=20, window_seconds=60)
    if not payload.message or not payload.message.strip():
        raise HTTPException(status_code=422, detail="Message cannot be empty")
    customer_id = _resolve_customer_id(request, db)

    def event_stream():
        for event in service.stream_chat_reply(
            db, payload.session_key, payload.message.strip(),
            customer_id=customer_id, page_url=payload.page_url,
        ):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/health")
def chatbot_health(db: Session = Depends(get_db)):
    from app.config import settings
    from app.models.chatbot import ChatEmbedding

    return {
        "llm_configured": bool(settings.ANTHROPIC_API_KEY),
        "llm_model": settings.CHATBOT_LLM_MODEL if settings.ANTHROPIC_API_KEY else None,
        "rag_indexed": db.query(ChatEmbedding).first() is not None,
    }


@router.post("/feedback", response_model=ChatFeedbackResponse)
def submit_chat_feedback(payload: ChatFeedbackCreate, request: Request, db: Session = Depends(get_db)):
    check_rate_limit(request, "chatbot-feedback", max_calls=30, window_seconds=60)
    feedback = service.submit_feedback(db, payload.message_id, payload.rating, payload.comment)
    if not feedback:
        raise HTTPException(status_code=404, detail="Message not found")
    return feedback


@router.post("/admin/reindex")
def admin_reindex(
    db: Session = Depends(get_db),
    _: object = Depends(require_any_permission("chatbot.edit", "update-chatbot")),
):
    """Rebuild the RAG vector index for tours + FAQs. Call after bulk tour
    imports/edits -- FAQ create/update/delete already keep themselves in sync."""
    stats = rag.reindex_all(db)
    return {"status": "success", **stats}


@router.get("/faqs", response_model=list[FAQResponse])
def public_faqs(db: Session = Depends(get_db)):
    return service.list_faqs(db, include_inactive=False)


# admin faq management
@router.get("/admin/faqs")
def admin_list_faqs(
    params: dict = Depends(pagination_params),
    is_public: bool | None = None,
    db: Session = Depends(get_db),
    _: object = Depends(require_any_permission("chatbot.view", "view-chatbot")),
):
    return {
        "status": "success",
        **service.list_faqs_paginated(
            db, page=params["page"], limit=params["limit"], search=params["search"],
            include_inactive=True, is_public=is_public,
        ),
    }


@router.post("/admin/faqs", response_model=FAQResponse, status_code=201)
def admin_create_faq(
    payload: FAQCreate,
    db: Session = Depends(get_db),
    _: object = Depends(require_any_permission("chatbot.create", "create-chatbot")),
):
    return service.create_faq(db, payload)


@router.put("/admin/faqs/{faq_id}", response_model=FAQResponse)
def admin_update_faq(
    faq_id: int,
    payload: FAQUpdate,
    db: Session = Depends(get_db),
    _: object = Depends(require_any_permission("chatbot.edit", "update-chatbot")),
):
    faq = service.update_faq(db, faq_id, payload)
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found")
    return faq


@router.delete("/admin/faqs/{faq_id}", status_code=204)
def admin_delete_faq(
    faq_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(require_any_permission("chatbot.delete", "delete-chatbot")),
):
    if not service.delete_faq(db, faq_id):
        raise HTTPException(status_code=404, detail="FAQ not found")


# admin chat session viewing
@router.get("/admin/sessions")
def admin_list_sessions(
    params: dict = Depends(pagination_params),
    db: Session = Depends(get_db),
    _: object = Depends(require_any_permission("chatbot.view", "view-chatbot")),
):
    return {"status": "success", **service.list_chat_sessions(db, params["page"], params["limit"])}


@router.get("/admin/sessions/{session_id}/messages")
def admin_session_messages(
    session_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(require_any_permission("chatbot.view", "view-chatbot")),
):
    return {"status": "success", "data": service.get_chat_session_messages(db, session_id)}
