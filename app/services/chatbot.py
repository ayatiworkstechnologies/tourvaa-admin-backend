import logging
import re
import secrets

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config import settings
from app.models.chatbot import ChatFAQ, ChatFeedback, ChatMessage, ChatSession
from app.schemas.chatbot import FAQCreate, FAQUpdate
from app.models.cms import Country, Tour
from app.models.website_cms import CustomerReview, PopularDestination, PopularTour

logger = logging.getLogger(__name__)

CHAT_RETENTION_DAYS = 90
# The scripted reply used when nothing matched - also how "unanswered" questions are found.
NO_ANSWER_REPLY = "I can help with Tourvaa tours, booking steps, pricing, cancellations, payments, and destinations. Could you share a little more detail?"

BOOKING_INFO_PHRASES = (
    "my booking", "my bookings", "my trip", "my order", "my reservation",
    "booking status", "my payment", "amount pending", "my invoice",
    "when do i travel", "my upcoming",
)

TRAVEL_GUIDE_PHRASES = (
    "plan a trip", "plan my trip", "trip planning", "travel guide",
    "build an itinerary", "make an itinerary", "travel itinerary",
    "things to do", "what should i pack", "what to pack", "packing list",
    "family trip", "family tour", "honeymoon", "couples trip", "solo trip",
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


def _is_travel_guide_request(user_message: str) -> bool:
    msg = _normalise(user_message)
    return any(phrase in msg for phrase in TRAVEL_GUIDE_PHRASES)


def _travel_guide_reply(db: Session, user_message: str) -> tuple[str, str | None, dict | None]:
    """Helpful, bounded travel-planning guidance when the visitor has not
    yet selected a specific Tourvaa product. Facts about a tour still come
    from the RAG/catalogue flow below; this only guides the next decision."""
    msg = _normalise(user_message)
    if "pack" in msg:
        return (
            "A good starting packing list is: travel documents, any visa or entry documents you need, medication, a reusable water bottle, weather-appropriate layers, comfortable walking shoes, a power adapter, and travel insurance details.\n\nTell me your destination, travel month, and tour style (city, beach, nature, or adventure) and I will tailor the list.",
            None,
            None,
        )

    if any(word in msg for word in ("family", "honeymoon", "couple", "solo")):
        tours = _top_tours(db, limit=4)
        reply = (
            "I can help you find the right trip. For a tailored recommendation, share your destination, travel dates, traveller ages, budget, and preferred pace.\n\n"
            "Here are a few popular tours to begin with - open one to check its itinerary and availability:"
        )
        return reply, "show_tours", {"tours": _tour_cards(tours)} if tours else None

    return (
        "I would love to help plan your trip. Send me these details and I will guide you to suitable tours:\n"
        "- Destination or region\n- Travel dates or month\n- Number of travellers and ages of children, if any\n- Interests (culture, food, wildlife, beach, adventure, or relaxation)\n- Approximate budget\n\nYou can also ask for popular destinations or top tours.",
        None,
        None,
    )


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


def _top_tours(db: Session, limit: int = 5) -> list[Tour]:
    """Prefer the admin-curated CMS "popular tours" list (same one the
    website homepage uses); fall back to featured/latest published tours
    when nothing has been curated yet."""
    curated = (
        db.query(Tour)
        .join(PopularTour, PopularTour.tour_id == Tour.id)
        .filter(PopularTour.is_active == True, Tour.status == "published")
        .order_by(PopularTour.sort_order, PopularTour.id)
        .limit(limit)
        .all()
    )
    if curated:
        return curated

    tours = (
        db.query(Tour)
        .filter(Tour.status == "published", Tour.featured == True)
        .order_by(Tour.id.desc())
        .limit(limit)
        .all()
    )
    if not tours:
        tours = db.query(Tour).filter(Tour.status == "published").order_by(Tour.id.desc()).limit(limit).all()
    return tours


def _top_countries(db: Session, limit: int = 8) -> list[str]:
    """Prefer the admin-curated CMS "popular destinations" list; fall back
    to the countries with the most published tours."""
    curated = (
        db.query(PopularDestination.title)
        .filter(PopularDestination.is_active == True)
        .order_by(PopularDestination.sort_order, PopularDestination.id)
        .limit(limit)
        .all()
    )
    if curated:
        return [title for (title,) in curated]

    rows = (
        db.query(Country.country_name, func.count(Tour.id).label("tour_count"))
        .join(Tour, Tour.country_id == Country.id)
        .filter(Tour.status == "published")
        .group_by(Country.country_name)
        .order_by(func.count(Tour.id).desc())
        .limit(limit)
        .all()
    )
    return [name for name, _count in rows]


def _why_tourvaa_text(db: Session) -> str:
    """Build the "why Tourvaa" answer from real review data in the DB
    instead of a static blurb, so it stays honest as reviews come in."""
    reviews = (
        db.query(CustomerReview)
        .filter(CustomerReview.is_active == True)
        .order_by(CustomerReview.rating.desc(), CustomerReview.sort_order)
        .limit(3)
        .all()
    )

    base = (
        "Why Tourvaa? We handpick and vet every tour, offer transparent pricing with no hidden fees, "
        "flexible booking with instant confirmation, secure payments, and dedicated support before, during, "
        "and after your trip."
    )

    if reviews:
        all_ratings = [r[0] for r in db.query(CustomerReview.rating).filter(CustomerReview.is_active == True).all()]
        avg_rating = sum(all_ratings) / len(all_ratings)
        base += f" Rated {avg_rating:.1f}/5 by {len(all_ratings)} travellers, including:\n"
        for r in reviews:
            quote = r.review_text.strip()
            if len(quote) > 140:
                quote = quote[:137].rstrip() + "..."
            base += f"\n- \"{quote}\" - {r.reviewer_name}" + (f", {r.tour_name}" if r.tour_name else "")
        base += "\n"

    base += "\nTell me a destination or travel date and I can show you tours to get started!"
    return base


BOOKING_PREFIXES = ("__select_tour__:", "__select_date__:", "__select_travellers__:")


def _available_dates(db: Session, tour: Tour, limit: int = 120) -> list[dict]:
    """Departure dates a customer can actually book: open, with seats left, in the
    future, past the tour's minimum-advance window, and not blacked out - the
    same rules the booking itself enforces."""
    from datetime import date, datetime, timedelta, timezone

    from app.models.tours import TourCalendar, TourUnavailableDate
    from app.services.tour_availability import min_advance_booking_days

    earliest = date.today() + timedelta(days=max(0, min_advance_booking_days(db, tour.id)))
    blackout = {
        row[0].date()
        for row in db.query(TourUnavailableDate.unavailable_date).filter(TourUnavailableDate.tour_id == tour.id).all()
        if row[0]
    }
    rows = (
        db.query(TourCalendar)
        .filter(
            TourCalendar.tour_id == tour.id,
            TourCalendar.status == "available",
            TourCalendar.available_seats > TourCalendar.booked_seats,
            TourCalendar.tour_date >= datetime.now(timezone.utc),
        )
        .order_by(TourCalendar.tour_date.asc())
        .all()
    )
    dates: list[dict] = []
    for row in rows:
        day = row.tour_date.date()
        if day < earliest or day in blackout:
            continue
        dates.append({"date": day.isoformat(), "slots": max(0, row.available_seats - row.booked_seats), "calendar_id": row.id})
        if len(dates) >= limit:
            break
    return dates


def _parse_booking_command(db: Session, user_message: str) -> tuple[str, str | None, dict | None] | None:
    """Handle structured booking-flow messages sent by the chat widget."""
    msg = user_message.strip()

    if msg.startswith("__select_tour__:"):
        tour_id_str = msg.replace("__select_tour__:", "").strip()
        try:
            tour_id = int(tour_id_str)
        except ValueError:
            return None
        tour = db.query(Tour).filter(Tour.id == tour_id, Tour.status == "published").first()
        if not tour:
            return "Sorry, that tour could not be found.", None, None
        available = _available_dates(db, tour)
        if not available:
            return (
                f"**{tour.title}** has no open departure dates right now. "
                f"You can open the tour page to check back later, or ask me about other tours.",
                None, None,
            )
        reply = f"Great choice - **{tour.title}**! Pick one of the available departure dates below."
        return reply, "select_date", {
            "tour_id": tour.id,
            "tour_title": tour.title,
            "available_dates": available,
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
        tour = db.query(Tour).filter(Tour.id == tour_id, Tour.status == "published").first()
        if not tour:
            return "Sorry, that tour could not be found.", None, None
        available = _available_dates(db, tour)
        if date_str not in {d["date"] for d in available}:
            return (
                f"Sorry, **{tour.title}** isn't available on {date_str}. Please choose one of the available dates.",
                "select_date",
                {
                    "tour_id": tour.id, "tour_title": tour.title, "available_dates": available,
                    "duration_days": tour.number_of_days,
                    "price": float(tour.price_start_per_person) if tour.price_start_per_person else None,
                    "currency": tour.currency or "USD",
                },
            )
        tour_title = tour.title
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
        tour = db.query(Tour).filter(Tour.id == tour_id, Tour.status == "published").first()
        if not tour:
            return "Sorry, that tour could not be found.", None, None
        slot = next((d for d in _available_dates(db, tour) if d["date"] == date_str), None)
        if not slot:
            return "Sorry, that date is no longer available. Please pick another date.", None, None

        # Quote with the same engine checkout uses (slabs, group tiers, discounts,
        # tax), so the total shown here is what the booking will actually charge.
        from fastapi import HTTPException
        from app.schemas.bookings import BookingCreate
        from app.services.bookings import calculate_booking_price

        try:
            quote = calculate_booking_price(db, BookingCreate(
                customer_id=0, tour_id=tour.id, tour_calendar_id=slot["calendar_id"],
                no_of_adults=travellers, adults_count=travellers, no_of_children=0, children_count=0,
                currency=tour.currency or "USD", booking_source="customer",
            ))
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, str) else "That group size isn't available for this date."
            return (
                f"Sorry, I couldn't price {travellers} traveller(s) for **{tour.title}** on {date_str}: {detail}",
                "select_travellers",
                {"tour_id": tour.id, "tour_title": tour.title, "date": date_str,
                 "price": float(tour.price_start_per_person) if tour.price_start_per_person else None,
                 "currency": tour.currency or "USD"},
            )
        currency = quote["currency"]
        total = float(quote["final_amount"])
        per_person = round(total / travellers, 2) if travellers else None
        lines = [
            "Here is your booking summary:",
            f"• Tour: {tour.title}",
            f"• Date: {date_str}",
            f"• Travellers: {travellers}",
            f"• Tour price: {currency} {float(quote['base_amount']):,.2f}",
        ]
        if float(quote["group_discount_amount"]) > 0:
            lines.append(f"• Group discount: -{currency} {float(quote['group_discount_amount']):,.2f}")
        if float(quote["discount_amount"]) > 0:
            lines.append(f"• Discount: -{currency} {float(quote['discount_amount']):,.2f}")
        if float(quote["tax_amount"]) > 0:
            lines.append(f"• Taxes & fees: {currency} {float(quote['tax_amount']):,.2f}")
        lines.append(f"• Total: {currency} {total:,.2f}")
        reply = "\n".join(lines) + "\n\nConfirm your booking below."
        return reply, "confirm_booking", {
            "tour_id": tour.id,
            "tour_title": tour.title,
            "date": date_str,
            "travellers": travellers,
            "price_per_person": per_person,
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

    if "why tourvaa" in msg or "benefit" in msg or "advantage" in msg or "why choose" in msg or "why book with" in msg:
        return _why_tourvaa_text(db), None, None

    if "review" in msg or "testimonial" in msg or "rating" in msg:
        return _why_tourvaa_text(db), None, None

    if "top" in msg or "best" in msg or "popular" in msg:
        if "countr" in msg or "destination" in msg:
            countries = _top_countries(db)
            if countries:
                reply = "Our most popular destinations are:\n" + "\n".join(f"- {c}" for c in countries)
                reply += "\n\nAsk me about any of these and I can show matching tours."
                return reply, None, None
        if "tour" in msg or "package" in msg or "trip" in msg:
            tours = _top_tours(db)
            if tours:
                reply = "Here are some of our top Tourvaa tours. Tap a tour to start booking:"
                return reply, "show_tours", {"tours": _tour_cards(tours)}

    if any(word in msg for word in ["tour", "trip", "book", "destination", "package", "show", "find", "search"]):
        reply, action_type, action_data = _tour_action(db, user_message)
        if action_type:
            return reply, action_type, action_data
        if "book" in msg or "booking" in msg:
            return "To book, open a tour, choose Book This Tour, sign in as a customer, select travel date and travellers, then confirm. Your booking will appear in the customer dashboard.", None, None

    tour_reply = _tour_fallback(db, user_message)
    if tour_reply:
        return tour_reply, None, None

    return NO_ANSWER_REPLY, None, None


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


_SMALLTALK_WORDS = frozenset("hello hi hey thanks thank you ok okay good morning afternoon evening bye goodbye cheers great".split())


def _is_smalltalk(user_message: str) -> bool:
    words = re.findall(r"[a-z]+", user_message.lower())
    return bool(words) and len(words) <= 4 and all(w in _SMALLTALK_WORDS for w in words)


def _answer_with_rag(
    db: Session,
    user_message: str,
    faqs: list[ChatFAQ],
    customer_id: int | None,
    page_url: str | None,
) -> tuple[str, str | None, dict | None]:
    """Answer from the site's own content (FAQs, Help Centre, pages, tours) via
    retrieval - see services/rag_answer.py. No external LLM is involved.
    Falls back to the scripted replies when retrieval finds nothing relevant."""
    if customer_id and _wants_booking_info(user_message):
        context = _get_customer_bookings_context(db, customer_id)
        if context.startswith("- ") or "\n- " in context:
            return "Here are your most recent bookings:\n" + context, None, None
        return context, None, None

    if _is_smalltalk(user_message):
        msg = _normalise(user_message)
        if "thank" in msg or "cheers" in msg:
            return "You're welcome! Let me know if there's anything else I can help with.", None, None
        if "bye" in msg:
            return "Goodbye! Have a great day, and happy travels.", None, None
        return _rule_based_reply(db, user_message, faqs)

    if _is_travel_guide_request(user_message):
        return _travel_guide_reply(db, user_message)

    from app.services import rag_answer

    try:
        result = rag_answer.answer(db, user_message, page_url)
    except Exception:
        logger.exception("RAG retrieval failed; using scripted fallback")
        result = None

    if result:
        action_type, action_data = None, None
        if result["tour_ids"]:
            tours = db.query(Tour).filter(Tour.id.in_(result["tour_ids"]), Tour.status == "published").all()
            order = {tid: i for i, tid in enumerate(result["tour_ids"])}
            tours.sort(key=lambda t: order.get(t.id, 99))
            if tours:
                action_type, action_data = "show_tours", {"tours": _tour_cards(tours)}
        return result["text"], action_type, action_data

    return _rule_based_reply(db, user_message, faqs)


def _stream_pieces(text: str, words_per_piece: int = 3):
    tokens = re.findall(r"\S+\s*", text)
    for i in range(0, len(tokens), words_per_piece):
        yield "".join(tokens[i:i + words_per_piece])


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

    reply_text, action_type, action_data = _answer_with_rag(db, user_message, faqs, customer_id, page_url)
    # Reply is stream-delivered in small pieces so the widget types it out.
    for piece in _stream_pieces(reply_text):
        yield {"type": "delta", "text": piece}

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


def _reindex_faq(db: Session, faq: ChatFAQ | None, faq_id: int | None = None) -> None:
    """Keep the keyword cache and (if built) the vector index in step with FAQ edits."""
    from app.services import rag, rag_answer

    rag_answer.invalidate()
    try:
        if faq is not None:
            rag.index_faq(db, faq)
        elif faq_id is not None:
            rag.delete_embedding(db, "faq", faq_id)
    except Exception:
        logger.warning("FAQ vector re-index failed", exc_info=True)


def create_faq(db: Session, data: FAQCreate) -> ChatFAQ:
    faq = ChatFAQ(**data.model_dump())
    db.add(faq)
    db.commit()
    db.refresh(faq)
    _reindex_faq(db, faq)
    return faq


def update_faq(db: Session, faq_id: int, data: FAQUpdate) -> ChatFAQ | None:
    faq = db.query(ChatFAQ).filter(ChatFAQ.id == faq_id).first()
    if not faq:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(faq, field, value)
    db.commit()
    db.refresh(faq)
    _reindex_faq(db, faq)
    return faq


def delete_faq(db: Session, faq_id: int) -> bool:
    faq = db.query(ChatFAQ).filter(ChatFAQ.id == faq_id).first()
    if not faq:
        return False
    db.delete(faq)
    db.commit()
    _reindex_faq(db, None, faq_id)
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


def chatbot_analytics(db: Session, days: int = 30, limit: int = 15) -> dict:
    """Numbers for the admin Insights tab: how the bot is doing and what to teach it."""
    from datetime import datetime, timedelta, timezone

    since = datetime.now(timezone.utc) - timedelta(days=days)

    def preceding_question(message: ChatMessage) -> str:
        q = (
            db.query(ChatMessage.content)
            .filter(ChatMessage.session_id == message.session_id, ChatMessage.role == "user", ChatMessage.id < message.id)
            .order_by(ChatMessage.id.desc())
            .first()
        )
        return q[0] if q else ""

    sessions = db.query(func.count(ChatSession.id)).filter(ChatSession.created_at >= since).scalar() or 0
    questions = (
        db.query(func.count(ChatMessage.id))
        .filter(ChatMessage.role == "user", ChatMessage.created_at >= since)
        .scalar()
        or 0
    )
    unanswered_msgs = (
        db.query(ChatMessage)
        .filter(ChatMessage.role == "assistant", ChatMessage.content == NO_ANSWER_REPLY, ChatMessage.created_at >= since)
        .order_by(ChatMessage.id.desc())
        .all()
    )
    up = db.query(func.count(ChatFeedback.id)).filter(ChatFeedback.rating > 0, ChatFeedback.created_at >= since).scalar() or 0
    down_rows = (
        db.query(ChatFeedback, ChatMessage)
        .join(ChatMessage, ChatFeedback.message_id == ChatMessage.id)
        .filter(ChatFeedback.rating < 0, ChatFeedback.created_at >= since)
        .order_by(ChatFeedback.id.desc())
        .all()
    )

    seen: dict[str, int] = {}
    for m in unanswered_msgs:
        q = _normalise(preceding_question(m))
        if q:
            seen[q] = seen.get(q, 0) + 1
    unanswered = [{"question": q, "count": n} for q, n in sorted(seen.items(), key=lambda kv: kv[1], reverse=True)[:limit]]

    return {
        "days": days,
        "sessions": sessions,
        "questions": questions,
        "unanswered_count": len(unanswered_msgs),
        "answer_rate": round(100 * (1 - len(unanswered_msgs) / questions), 1) if questions else None,
        "thumbs_up": up,
        "thumbs_down": len(down_rows),
        "unanswered": unanswered,
        "disliked": [
            {"question": preceding_question(m), "answer": m.content[:300], "comment": fb.comment or ""}
            for fb, m in down_rows[:limit]
        ],
    }


def purge_old_chat_data(db: Session, days: int = CHAT_RETENTION_DAYS) -> int:
    """Delete chat sessions (with their messages and feedback) with no activity in `days` days."""
    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    last_activity = (
        db.query(ChatMessage.session_id.label("sid"), func.max(ChatMessage.created_at).label("last"))
        .group_by(ChatMessage.session_id)
        .subquery()
    )
    old_ids = [
        sid for (sid,) in db.query(ChatSession.id)
        .outerjoin(last_activity, last_activity.c.sid == ChatSession.id)
        .filter(func.coalesce(last_activity.c.last, ChatSession.created_at) < cutoff)
        .all()
    ]
    if not old_ids:
        return 0
    msg_ids = [mid for (mid,) in db.query(ChatMessage.id).filter(ChatMessage.session_id.in_(old_ids)).all()]
    if msg_ids:
        db.query(ChatFeedback).filter(ChatFeedback.message_id.in_(msg_ids)).delete(synchronize_session=False)
    db.query(ChatFeedback).filter(ChatFeedback.session_id.in_(old_ids)).delete(synchronize_session=False)
    db.query(ChatMessage).filter(ChatMessage.session_id.in_(old_ids)).delete(synchronize_session=False)
    db.query(ChatSession).filter(ChatSession.id.in_(old_ids)).delete(synchronize_session=False)
    db.commit()
    logger.info("Chat retention: removed %d session(s) older than %d days", len(old_ids), days)
    return len(old_ids)
