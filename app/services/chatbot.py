import logging
import re
import secrets

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config import settings
from app.models.chatbot import ChatFAQ, ChatFeedback, ChatMessage, ChatSession
from app.schemas.chatbot import FAQCreate, FAQUpdate
from app.models.cms import Tour

logger = logging.getLogger(__name__)

HISTORY_WINDOW = 10

BOOKING_INFO_PHRASES = (
    "my booking", "my bookings", "my trip", "my order", "my reservation",
    "booking status", "my payment", "amount pending", "my invoice",
    "when do i travel", "my upcoming",
)


def _normalise(value: str) -> str:
    return " ".join(value.lower().strip().split())


def _keyword_score(message: str, *texts: str | None) -> int:
    words = {w for w in _normalise(message).replace("?", "").replace(",", "").split() if len(w) > 2}
    haystack = _normalise(" ".join(t or "" for t in texts))
    return sum(1 for word in words if word in haystack)


def _wants_booking_info(user_message: str) -> bool:
    msg = _normalise(user_message)
    return any(phrase in msg for phrase in BOOKING_INFO_PHRASES)


def _get_customer_bookings_context(db: Session, customer_id: int) -> str:
    from app.models.bookings import Booking

    bookings = (
        db.query(Booking)
        .filter(Booking.customer_id == customer_id)
        .order_by(Booking.id.desc())
        .limit(5)
        .all()
    )
    if not bookings:
        return "This logged-in customer has no bookings yet."

    lines = []
    for b in bookings:
        travel_date = b.tour_date or (b.tour_start_date.date().isoformat() if b.tour_start_date else "TBD")
        total = b.final_amount or b.total_cost or 0
        lines.append(
            f"- Booking {b.booking_code or ('#' + str(b.id))}: {b.tour_name or 'Tour'}, "
            f"travel date {travel_date}, status: {b.booking_status}, payment: {b.payment_status}, "
            f"total: {b.currency} {total}, pending: {b.currency} {b.amount_pending or 0}."
        )
    return "\n".join(lines)


_TOUR_PAGE_URL_RE = re.compile(r"/tours/(\d+)")


def _page_context(db: Session, page_url: str | None) -> str | None:
    """Best-effort: if the visitor is currently on a tour detail page, surface
    that tour so the assistant can answer page-specific questions ("is
    breakfast included?") without the customer having to name the tour."""
    if not page_url:
        return None
    match = _TOUR_PAGE_URL_RE.search(page_url)
    if not match:
        return None
    tour = db.query(Tour).filter(Tour.id == int(match.group(1)), Tour.status == "published").first()
    if not tour:
        return None
    price = f"{tour.currency} {tour.price_start_per_person:,.0f}" if tour.price_start_per_person else "price on request"
    return (
        f"{tour.title} ({tour.number_of_days} day(s), starting from {price}). "
        f"{tour.short_description or ''}".strip()
    )


def _build_system_prompt(
    faq_snippets: list[str],
    tour_snippets: list[str],
    booking_context: str | None,
    page_context: str | None = None,
) -> str:
    base = (
        "You are a friendly and knowledgeable travel assistant for Tourvaa, "
        "a premium tour and travel booking platform. "
        "Ground your answers in the retrieved context below when it is relevant. If the context does not "
        "cover the question, answer briefly from general travel knowledge and encourage the customer to "
        "contact the Tourvaa support team for anything account-specific. Be concise, warm, and helpful.\n\n"
    )
    if page_context:
        base += (
            "The customer is currently viewing this tour's page. If their question is ambiguous "
            "(e.g. \"is breakfast included\", \"how many days\"), assume it refers to this tour:\n\n"
            + page_context + "\n\n"
        )
    if faq_snippets:
        base += "Relevant FAQs (retrieved for this question):\n\n" + "\n\n".join(faq_snippets) + "\n\n"
    if tour_snippets:
        base += "Relevant Tourvaa tours (retrieved for this question):\n\n" + "\n\n".join(tour_snippets) + "\n\n"
    if booking_context:
        base += (
            "The customer is logged in. Only use the following when they ask about their own "
            "bookings -- never invent or guess booking details:\n\n" + booking_context + "\n\n"
        )
    return base


def _faq_fallback(user_message: str, faqs: list[ChatFAQ]) -> str | None:
    if not faqs:
        return None
    ranked = sorted(
        faqs,
        key=lambda faq: _keyword_score(user_message, faq.question, faq.answer, faq.category),
        reverse=True,
    )
    best = ranked[0]
    if _keyword_score(user_message, best.question, best.answer, best.category) >= 2:
        return best.answer
    return None


def _search_tours(db: Session, user_message: str) -> list[Tour]:
    msg = _normalise(user_message)
    words = [word for word in msg.split() if len(word) > 2]
    query = db.query(Tour).filter(Tour.status == "published")
    if words:
        filters = []
        for word in words[:5]:
            pattern = f"%{word}%"
            filters.extend([
                Tour.title.ilike(pattern),
                Tour.subtitle.ilike(pattern),
                Tour.short_description.ilike(pattern),
                Tour.long_description.ilike(pattern),
            ])
        query = query.filter(or_(*filters))
    tours = query.order_by(Tour.id.desc()).limit(4).all()
    if not tours:
        tours = db.query(Tour).filter(Tour.status == "published").order_by(Tour.id.desc()).limit(4).all()
    return tours


def _tour_cards(tours: list[Tour]) -> list[dict]:
    cards = []
    for t in tours:
        price = float(t.price_start_per_person) if t.price_start_per_person else None
        cards.append({
            "id": t.id,
            "title": t.title,
            "duration_days": t.number_of_days,
            "price": price,
            "currency": t.currency or "USD",
            "cover_image": t.banner_image or None,
            "slug": t.slug or str(t.id),
        })
    return cards


def _tour_action(db: Session, user_message: str) -> tuple[str, str | None, dict | None]:
    msg = _normalise(user_message)
    wants_tour = any(word in msg for word in ["tour", "trip", "dubai", "price", "cost", "book", "destination", "package", "days"])
    if not wants_tour:
        return "", None, None

    tours = _search_tours(db, user_message)
    if not tours:
        return "", None, None

    reply = "Here are some Tourvaa tours that match your request. Tap a tour to start booking:"
    return reply, "show_tours", {"tours": _tour_cards(tours)}


def _tour_fallback(db: Session, user_message: str) -> str | None:
    msg = _normalise(user_message)
    wants_tour = any(word in msg for word in ["tour", "trip", "dubai", "price", "cost", "book", "destination", "package", "days"])
    if not wants_tour:
        return None

    tours = _search_tours(db, user_message)
    if not tours:
        return None

    lines = ["Here are a few Tourvaa tours you can explore:"]
    for tour in tours:
        price = f"{tour.currency} {tour.price_start_per_person:,.0f}" if tour.price_start_per_person else "price on request"
        duration = f"{tour.number_of_days} day" + ("s" if tour.number_of_days != 1 else "")
        lines.append(f"- {tour.title}: {duration}, starting from {price}. Open /tours/{tour.id} to view details or book.")
    lines.append("Share your destination, travel date, and traveller count if you want a narrower suggestion.")
    return "\n".join(lines)


SHOW_TOURS_TOOL = {
    "name": "show_tours",
    "description": (
        "Search Tourvaa's published tours and show the matching tours as cards in the chat UI. "
        "Call this whenever the customer is asking about tours, destinations, prices, packages, or wants "
        "to browse or start booking something -- even if the request is indirect (e.g. 'what can I do in "
        "Dubai', 'something for a family of 4', 'any cheaper options', 'show me more'). "
        "Do not call it for general FAQ, cancellation, payment, or account questions -- answer those with text."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "A short search query capturing what the customer is looking for: destination, theme, budget, duration, etc.",
            }
        },
        "required": ["query"],
    },
}

BOOKING_PREFIXES = ("__select_tour__:", "__select_date__:", "__select_travellers__:")


def _parse_booking_command(db: Session, user_message: str) -> tuple[str, str | None, dict | None] | None:
    """Handle structured booking-flow messages sent by the chat widget."""
    msg = user_message.strip()

    if msg.startswith("__select_tour__:"):
        tour_id_str = msg.replace("__select_tour__:", "").strip()
        try:
            tour_id = int(tour_id_str)
        except ValueError:
            return None
        tour = db.query(Tour).filter(Tour.id == tour_id).first()
        if not tour:
            return "Sorry, that tour could not be found.", None, None
        reply = f"Great choice - **{tour.title}**! What date are you planning to travel? (e.g. 15 July 2025)"
        return reply, "select_date", {
            "tour_id": tour.id,
            "tour_title": tour.title,
            "duration_days": tour.number_of_days,
            "price": float(tour.price_start_per_person) if tour.price_start_per_person else None,
            "currency": tour.currency or "USD",
        }

    if msg.startswith("__select_date__:"):
        payload = msg.replace("__select_date__:", "").strip()
        try:
            parts = dict(p.split("=", 1) for p in payload.split("|"))
            tour_id = int(parts["tour_id"])
            date_str = parts["date"]
        except Exception:
            return None
        tour = db.query(Tour).filter(Tour.id == tour_id).first()
        tour_title = tour.title if tour else "the tour"
        reply = f"How many travellers will be joining for **{tour_title}** on **{date_str}**?"
        return reply, "select_travellers", {
            "tour_id": tour_id,
            "tour_title": tour_title,
            "date": date_str,
            "price": float(tour.price_start_per_person) if tour and tour.price_start_per_person else None,
            "currency": (tour.currency if tour else None) or "USD",
        }

    if msg.startswith("__select_travellers__:"):
        payload = msg.replace("__select_travellers__:", "").strip()
        try:
            parts = dict(p.split("=", 1) for p in payload.split("|"))
            tour_id = int(parts["tour_id"])
            travellers = int(parts["travellers"])
            date_str = parts["date"]
        except Exception:
            return None
        tour = db.query(Tour).filter(Tour.id == tour_id).first()
        tour_title = tour.title if tour else "the tour"
        price_per = float(tour.price_start_per_person) if tour and tour.price_start_per_person else None
        currency = (tour.currency if tour else None) or "USD"
        total = price_per * travellers if price_per else None
        total_str = f"{currency} {total:,.0f}" if total else "price on request"
        reply = (
            f"Here is your booking summary:\n"
            f"• Tour: {tour_title}\n"
            f"• Date: {date_str}\n"
            f"• Travellers: {travellers}\n"
            f"• Total: {total_str}\n\n"
            f"Confirm your booking below."
        )
        return reply, "confirm_booking", {
            "tour_id": tour_id,
            "tour_title": tour_title,
            "date": date_str,
            "travellers": travellers,
            "price_per_person": price_per,
            "total_price": total,
            "currency": currency,
        }

    return None


def _rule_based_reply(db: Session, user_message: str, faqs: list[ChatFAQ]) -> tuple[str, str | None, dict | None]:
    msg = _normalise(user_message)

    faq_reply = _faq_fallback(user_message, faqs)
    if faq_reply:
        return faq_reply, None, None

    if any(word in msg for word in ["hello", "hi", "hey"]):
        return "Hi, welcome to Tourvaa. I can help with tours, prices, booking steps, cancellations, payments, and support. What are you planning?", None, None
    if "cancel" in msg or "refund" in msg:
        return "Cancellation and refund rules can vary by tour. Open the tour page or your customer dashboard to review the booking, and contact support if travel is close.", None, None
    if "payment" in msg or "pay" in msg:
        return "Payments and pending balances are shown in your customer dashboard. If a payment is pending, our team can confirm payment options and next steps.", None, None

    if any(word in msg for word in ["tour", "trip", "book", "destination", "package", "show", "find", "search"]):
        reply, action_type, action_data = _tour_action(db, user_message)
        if action_type:
            return reply, action_type, action_data
        if "book" in msg or "booking" in msg:
            return "To book, open a tour, choose Book This Tour, sign in as a customer, select travel date and travellers, then confirm. Your booking will appear in the customer dashboard.", None, None

    tour_reply = _tour_fallback(db, user_message)
    if tour_reply:
        return tour_reply, None, None

    return "I can help with Tourvaa tours, booking steps, pricing, cancellations, payments, and destinations. Could you share a little more detail?", None, None


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


def stream_chat_reply(
    db: Session,
    session_key: str | None,
    user_message: str,
    customer_id: int | None = None,
    page_url: str | None = None,
):
    """Generator yielding incremental chat events as dicts:
    - {"type": "delta", "text": str}           -- a chunk of reply text to append
    - {"type": "done", "session_key": str, "action_type": str | None, "action_data": dict | None}
    Always ends with exactly one "done" event."""
    session = get_or_create_session(db, session_key)

    is_booking_command = any(user_message.strip().startswith(p) for p in BOOKING_PREFIXES)

    if not is_booking_command:
        db.add(ChatMessage(session_id=session.id, role="user", content=user_message))
        db.commit()

    action_type: str | None = None
    action_data: dict | None = None

    if is_booking_command:
        result = _parse_booking_command(db, user_message)
        if result:
            reply_text, action_type, action_data = result
        else:
            reply_text = "Sorry, I could not process that request. Please try again."
        yield {"type": "delta", "text": reply_text}
        assistant_message = ChatMessage(session_id=session.id, role="assistant", content=reply_text)
        db.add(assistant_message)
        db.commit()
        db.refresh(assistant_message)
        yield {
            "type": "done", "session_key": session.session_key, "action_type": action_type,
            "action_data": action_data, "message_id": assistant_message.id,
        }
        return

    faqs = get_active_faqs(db)
    faq_snippets = [f"Q: {f.question}\nA: {f.answer}" for f in faqs]

    tour_snippets: list[str] = []

    booking_context = None
    if customer_id and _wants_booking_info(user_message):
        booking_context = _get_customer_bookings_context(db, customer_id)

    page_context = _page_context(db, page_url)
    system_prompt = _build_system_prompt(faq_snippets, tour_snippets, booking_context, page_context)

    history = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.id.desc())
        .limit(HISTORY_WINDOW * 2)
        .all()
    )
    history = list(reversed(history))
    messages = [{"role": m.role, "content": m.content} for m in history]

    reply_text = ""

    if not settings.ANTHROPIC_API_KEY:
        logger.info("ANTHROPIC_API_KEY is not configured; using local chatbot fallback")
        reply_text, action_type, action_data = _rule_based_reply(db, user_message, faqs)
        yield {"type": "delta", "text": reply_text}
    else:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
            call_messages = list(messages)

            with client.messages.stream(
                model=settings.CHATBOT_LLM_MODEL,
                max_tokens=512,
                system=system_prompt,
                messages=call_messages,
                tools=[SHOW_TOURS_TOOL],
            ) as stream:
                for text in stream.text_stream:
                    reply_text += text
                    yield {"type": "delta", "text": text}
                final = stream.get_final_message()

            if final.stop_reason == "tool_use":
                tool_use = next(b for b in final.content if b.type == "tool_use")
                search_query = (tool_use.input or {}).get("query") or user_message
                tours = _search_tours(db, search_query)

                if tours:
                    action_type, action_data = "show_tours", {"tours": _tour_cards(tours)}
                    tool_result_content = f"Found {len(tours)} matching published tour(s)."
                else:
                    tool_result_content = "No matching published tours were found."

                call_messages.append({"role": "assistant", "content": final.content})
                call_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": tool_result_content,
                    }],
                })
                with client.messages.stream(
                    model=settings.CHATBOT_LLM_MODEL,
                    max_tokens=512,
                    system=system_prompt,
                    messages=call_messages,
                ) as followup_stream:
                    for text in followup_stream.text_stream:
                        reply_text += text
                        yield {"type": "delta", "text": text}

                if not reply_text.strip():
                    reply_text = (
                        "Here are some Tourvaa tours that match your request. Tap a tour to start booking:"
                        if tours else
                        "I could not find a published tour matching that. Could you share a destination or budget?"
                    )
                    yield {"type": "delta", "text": reply_text}
        except Exception as exc:
            logger.error("Anthropic API error: %s", exc)
            reply_text, action_type, action_data = _rule_based_reply(db, user_message, faqs)
            yield {"type": "delta", "text": reply_text}

    assistant_message = ChatMessage(session_id=session.id, role="assistant", content=reply_text)
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)
    yield {
        "type": "done", "session_key": session.session_key, "action_type": action_type,
        "action_data": action_data, "message_id": assistant_message.id,
    }


def submit_feedback(db: Session, message_id: int, rating: int, comment: str | None) -> ChatFeedback | None:
    """Record (or update) a thumbs up/down on an assistant message. Returns
    None if the message doesn't exist or isn't an assistant reply."""
    msg = db.query(ChatMessage).filter(ChatMessage.id == message_id, ChatMessage.role == "assistant").first()
    if not msg:
        return None

    feedback = db.query(ChatFeedback).filter(ChatFeedback.message_id == message_id).first()
    if feedback:
        feedback.rating = rating
        feedback.comment = comment
    else:
        feedback = ChatFeedback(message_id=message_id, session_id=msg.session_id, rating=rating, comment=comment)
        db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback


def list_faqs(db: Session, include_inactive: bool = False) -> list[ChatFAQ]:
    q = db.query(ChatFAQ)
    if not include_inactive:
        q = q.filter(ChatFAQ.is_active == True, ChatFAQ.is_public == True)
    return q.order_by(ChatFAQ.sort_order, ChatFAQ.id).all()


def list_faqs_paginated(
    db: Session,
    page: int = 1,
    limit: int = 20,
    search: str = "",
    include_inactive: bool = True,
    is_public: bool | None = None,
) -> dict:
    from app.utils.pagination import paginated_response

    q = db.query(ChatFAQ)
    if not include_inactive:
        q = q.filter(ChatFAQ.is_active == True)
    if is_public is not None:
        q = q.filter(ChatFAQ.is_public == is_public)
    if search:
        pattern = f"%{search.strip().lower()}%"
        q = q.filter(func.lower(ChatFAQ.question).like(pattern))
    q = q.order_by(ChatFAQ.sort_order, ChatFAQ.id)
    total = q.count()
    items = q.offset((page - 1) * limit).limit(limit).all()
    return paginated_response(items=items, total=total, page=page, limit=limit)


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


def list_chat_sessions(db: Session, page: int, limit: int):
    from math import ceil
    from sqlalchemy import func as sqlfunc

    message_count = (
        db.query(ChatMessage.session_id, sqlfunc.count(ChatMessage.id).label("message_count"))
        .group_by(ChatMessage.session_id)
        .subquery()
    )
    query = (
        db.query(ChatSession, message_count.c.message_count)
        .outerjoin(message_count, message_count.c.session_id == ChatSession.id)
        .order_by(ChatSession.id.desc())
    )
    total = query.count()
    rows = query.offset((page - 1) * limit).limit(limit).all()
    items = [
        {
            "id": session.id,
            "session_key": session.session_key,
            "user_name": session.user_name,
            "user_email": session.user_email,
            "message_count": count or 0,
            "created_at": session.created_at,
        }
        for session, count in rows
    ]
    return {"items": items, "total": total, "page": page, "limit": limit, "total_pages": max(1, ceil(total / limit))}


def get_chat_session_messages(db: Session, session_id: int) -> list[dict]:
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.id.asc())
        .all()
    )
    return [
        {"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at}
        for m in messages
    ]
