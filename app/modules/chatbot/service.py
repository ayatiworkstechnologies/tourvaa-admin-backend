import secrets
import logging
from sqlalchemy.orm import Session

from app.config import settings
from app.modules.chatbot.models import ChatFAQ, ChatMessage, ChatSession
from app.modules.chatbot.schemas import FAQCreate, FAQUpdate

logger = logging.getLogger(__name__)

HISTORY_WINDOW = 10  # last N message pairs to send as context


def _build_system_prompt(faqs: list[ChatFAQ]) -> str:
    base = (
        "You are a friendly and knowledgeable travel assistant for Tourvaa, "
        "a premium tour and travel booking platform. "
        "Help customers with questions about tours, bookings, destinations, pricing, and policies. "
        "Be concise, warm, and helpful. If you don't know something specific, encourage the customer "
        "to contact the Tourvaa support team.\n\n"
    )

    if faqs:
        faq_block = "Below are common questions and answers you should use when relevant:\n\n"
        for faq in faqs:
            faq_block += f"Q: {faq.question}\nA: {faq.answer}\n\n"
        return base + faq_block

    return base


def get_or_create_session(db: Session, session_key: str | None) -> ChatSession:
    if session_key:
        session = db.query(ChatSession).filter(ChatSession.session_key == session_key).first()
        if session:
            return session

    key = secrets.token_hex(32)
    session = ChatSession(session_key=key)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_active_faqs(db: Session) -> list[ChatFAQ]:
    return (
        db.query(ChatFAQ)
        .filter(ChatFAQ.is_active == True)
        .order_by(ChatFAQ.sort_order, ChatFAQ.id)
        .all()
    )


def get_chat_reply(db: Session, session_key: str | None, user_message: str) -> tuple[str, str]:
    session = get_or_create_session(db, session_key)

    user_msg = ChatMessage(session_id=session.id, role="user", content=user_message)
    db.add(user_msg)
    db.commit()

    faqs = get_active_faqs(db)
    system_prompt = _build_system_prompt(faqs)

    history = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.id.desc())
        .limit(HISTORY_WINDOW * 2)
        .all()
    )
    history = list(reversed(history))

    messages = [{"role": m.role, "content": m.content} for m in history]

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=512,
            system=system_prompt,
            messages=messages,
        )
        reply_text = response.content[0].text
    except Exception as exc:
        logger.error("Anthropic API error: %s", exc)
        reply_text = (
            "I'm sorry, I'm having trouble connecting right now. "
            "Please try again in a moment or contact our support team."
        )

    assistant_msg = ChatMessage(session_id=session.id, role="assistant", content=reply_text)
    db.add(assistant_msg)
    db.commit()

    return reply_text, session.session_key


# ── FAQ admin helpers ────────────────────────────────────────────────────────

def list_faqs(db: Session, include_inactive: bool = False) -> list[ChatFAQ]:
    q = db.query(ChatFAQ)
    if not include_inactive:
        q = q.filter(ChatFAQ.is_active == True)
    return q.order_by(ChatFAQ.sort_order, ChatFAQ.id).all()


def create_faq(db: Session, data: FAQCreate) -> ChatFAQ:
    faq = ChatFAQ(**data.model_dump())
    db.add(faq)
    db.commit()
    db.refresh(faq)
    return faq


def update_faq(db: Session, faq_id: int, data: FAQUpdate) -> ChatFAQ | None:
    faq = db.query(ChatFAQ).filter(ChatFAQ.id == faq_id).first()
    if not faq:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(faq, field, value)
    db.commit()
    db.refresh(faq)
    return faq


def delete_faq(db: Session, faq_id: int) -> bool:
    faq = db.query(ChatFAQ).filter(ChatFAQ.id == faq_id).first()
    if not faq:
        return False
    db.delete(faq)
    db.commit()
    return True
