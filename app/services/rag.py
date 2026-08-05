"""RAG indexing and retrieval over tours and FAQs.

Flow: index_* / reindex_all embed source rows into chat_embeddings;
semantic_search embeds the user's message once and ranks stored vectors by
cosine similarity in Python (see app/services/embeddings.py for why -- MySQL
has no vector type here). Callers in app/services/chatbot.py consume the
results to build a grounded system prompt and to resolve tour cards.
"""

import hashlib
import logging

from sqlalchemy.orm import Session

from app.models.chatbot import ChatEmbedding, ChatFAQ
from app.models.cms import Tour
from app.services.embeddings import cosine_similarity, embed_query, embed_texts

logger = logging.getLogger(__name__)

DEFAULT_MIN_SCORE = 0.35


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _tour_document(tour: Tour) -> str:
    parts = [
        tour.title,
        tour.subtitle,
        tour.short_description,
        tour.long_description,
        f"Start location: {tour.start_location}" if tour.start_location else "",
        f"Duration: {tour.number_of_days} day(s)" if tour.number_of_days else "",
        f"Starting price: {tour.currency} {tour.price_start_per_person}" if tour.price_start_per_person else "",
    ]
    return "\n".join(p for p in parts if p)


def _faq_document(faq: ChatFAQ) -> str:
    return f"Q: {faq.question}\nA: {faq.answer}"


def upsert_embedding(db: Session, source_type: str, source_id: int, text: str) -> None:
    text = (text or "").strip()
    if not text:
        delete_embedding(db, source_type, source_id)
        return

    content_hash = _hash(text)
    row = (
        db.query(ChatEmbedding)
        .filter(ChatEmbedding.source_type == source_type, ChatEmbedding.source_id == source_id)
        .first()
    )
    if row and row.content_hash == content_hash:
        return  # unchanged since last index -- skip the (relatively costly) embed call

    try:
        vector = embed_texts([text])[0]
    except Exception:
        logger.exception("Failed to embed %s:%s -- leaving unindexed", source_type, source_id)
        return

    if row:
        row.content_text = text
        row.content_hash = content_hash
        row.embedding = vector
    else:
        db.add(
            ChatEmbedding(
                source_type=source_type,
                source_id=source_id,
                content_text=text,
                content_hash=content_hash,
                embedding=vector,
            )
        )
    db.commit()


def delete_embedding(db: Session, source_type: str, source_id: int) -> None:
    db.query(ChatEmbedding).filter(
        ChatEmbedding.source_type == source_type, ChatEmbedding.source_id == source_id
    ).delete()
    db.commit()


def index_tour(db: Session, tour: Tour) -> None:
    """Keep a single tour's embedding in sync. Safe to call after any tour write."""
    if tour.status != "published":
        delete_embedding(db, "tour", tour.id)
        return
    upsert_embedding(db, "tour", tour.id, _tour_document(tour))


def index_faq(db: Session, faq: ChatFAQ) -> None:
    if not faq.is_active:
        delete_embedding(db, "faq", faq.id)
        return
    upsert_embedding(db, "faq", faq.id, _faq_document(faq))


def reindex_all(db: Session) -> dict:
    """Full rebuild -- used by the admin reindex endpoint and first-run bootstrap."""
    tours = db.query(Tour).filter(Tour.status == "published").all()
    for tour in tours:
        upsert_embedding(db, "tour", tour.id, _tour_document(tour))

    faqs = db.query(ChatFAQ).filter(ChatFAQ.is_active == True).all()
    for faq in faqs:
        upsert_embedding(db, "faq", faq.id, _faq_document(faq))

    valid_tour_ids = {t.id for t in tours}
    stale_tours = (
        db.query(ChatEmbedding)
        .filter(ChatEmbedding.source_type == "tour", ~ChatEmbedding.source_id.in_(valid_tour_ids or [0]))
        .all()
    )
    for row in stale_tours:
        db.delete(row)

    valid_faq_ids = {f.id for f in faqs}
    stale_faqs = (
        db.query(ChatEmbedding)
        .filter(ChatEmbedding.source_type == "faq", ~ChatEmbedding.source_id.in_(valid_faq_ids or [0]))
        .all()
    )
    for row in stale_faqs:
        db.delete(row)

    db.commit()
    return {"tours_indexed": len(tours), "faqs_indexed": len(faqs)}


def semantic_search(
    db: Session,
    query: str,
    source_types: list[str],
    top_k: int = 5,
    min_score: float = DEFAULT_MIN_SCORE,
) -> list[dict]:
    rows = db.query(ChatEmbedding).filter(ChatEmbedding.source_type.in_(source_types)).all()
    if not rows:
        return []

    try:
        query_vector = embed_query(query)
    except Exception:
        logger.exception("Failed to embed chat query for semantic search")
        return []

    scored = []
    for row in rows:
        score = cosine_similarity(query_vector, row.embedding)
        if score >= min_score:
            scored.append((score, row))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [
        {
            "source_type": row.source_type,
            "source_id": row.source_id,
            "content": row.content_text,
            "score": score,
        }
        for score, row in scored[:top_k]
    ]
