from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.chatbot import ChatFAQ, ChatFeedback, ChatMessage, ChatSession
from app.schemas.chatbot import ChatFeedbackCreate, FAQCreate
from app.services.chatbot import DuplicateFAQError, _tour_public_path, create_faq, get_active_faqs, submit_feedback


def test_feedback_requires_the_owning_chat_session_key():
    with pytest.raises(ValidationError):
        ChatFeedbackCreate(message_id=42, rating=1)

    payload = ChatFeedbackCreate(message_id=42, session_key="a" * 64, rating=-1)
    assert payload.session_key == "a" * 64
    assert payload.rating == -1


def test_chatbot_tour_links_use_the_canonical_country_and_slug_route():
    tour = SimpleNamespace(
        id=42,
        slug="coastal-discovery",
        country=SimpleNamespace(slug="new-zealand"),
    )
    assert _tour_public_path(tour) == "/tours/new-zealand/coastal-discovery"


def test_chatbot_tour_links_keep_a_safe_legacy_fallback_for_incomplete_data():
    tour = SimpleNamespace(id=42, slug="coastal-discovery", country=None)
    assert _tour_public_path(tour) == "/tours/42"


def test_feedback_cannot_be_written_for_a_different_chat_session():
    engine = create_engine("sqlite://")
    ChatSession.__table__.create(engine)
    ChatMessage.__table__.create(engine)
    ChatFeedback.__table__.create(engine)
    db = Session(engine)
    try:
        owner = ChatSession(session_key="a" * 64)
        visitor = ChatSession(session_key="b" * 64)
        db.add_all((owner, visitor))
        db.flush()
        message = ChatMessage(session_id=owner.id, role="assistant", content="How can I help?")
        db.add(message)
        db.commit()

        assert submit_feedback(db, message.id, visitor.session_key, 1, None) is None

        feedback = submit_feedback(db, message.id, owner.session_key, 1, "Useful")
        assert feedback is not None
        assert feedback.session_id == owner.id
    finally:
        db.close()
        engine.dispose()


def test_duplicate_faq_questions_are_rejected_and_historical_duplicates_are_deweighted():
    engine = create_engine("sqlite://")
    ChatFAQ.__table__.create(engine)
    db = Session(engine)
    try:
        first = ChatFAQ(question="How do I book?", answer="Use checkout.", sort_order=1, is_active=True)
        legacy_duplicate = ChatFAQ(question="  how   do I BOOK? ", answer="Old answer.", sort_order=2, is_active=True)
        db.add_all((first, legacy_duplicate))
        db.commit()

        assert [faq.id for faq in get_active_faqs(db)] == [first.id]
        with pytest.raises(DuplicateFAQError):
            create_faq(db, FAQCreate(question="How do I book?", answer="Another answer."))
    finally:
        db.close()
        engine.dispose()
