from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.permissions import require_any_permission
from app.utils.ratelimit import check_rate_limit
from app.schemas.chatbot import (
    ChatMessageRequest,
    ChatMessageResponse,
    FAQCreate,
    FAQResponse,
    FAQUpdate,
)
from app.services import chatbot as service

router = APIRouter(prefix="/chatbot", tags=["Chatbot"])


@router.post("/chat", response_model=ChatMessageResponse)
def chat(payload: ChatMessageRequest, request: Request, db: Session = Depends(get_db)):
    check_rate_limit(request, "chatbot-chat", max_calls=20, window_seconds=60)
    if not payload.message or not payload.message.strip():
        raise HTTPException(status_code=422, detail="Message cannot be empty")
    reply, session_key, action_type, action_data = service.get_chat_reply(db, payload.session_key, payload.message.strip())
    return ChatMessageResponse(reply=reply, session_key=session_key, action_type=action_type, action_data=action_data)


@router.get("/faqs", response_model=list[FAQResponse])
def public_faqs(db: Session = Depends(get_db)):
    return service.list_faqs(db, include_inactive=False)


# admin faq management
@router.get("/admin/faqs", response_model=list[FAQResponse])
def admin_list_faqs(
    db: Session = Depends(get_db),
    _: object = Depends(require_any_permission("chatbot.view", "view-chatbot")),
):
    return service.list_faqs(db, include_inactive=True)


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
