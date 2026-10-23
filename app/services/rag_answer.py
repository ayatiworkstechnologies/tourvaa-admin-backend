"""Retrieval-augmented answers for the website chatbot - no external LLM.

Pipeline (see services/chatbot.py for where it plugs in):

  1. Knowledge base: chat FAQs, Help Centre articles, published CMS pages
     (policies, About, ...) and published tours, split into small chunks.
  2. Retrieval: BM25 keyword ranking over the chunks, fused (reciprocal rank)
     with the semantic vector search from services/rag.py when the embedding
     index exists. Keyword retrieval works on live DB rows with no indexing
     step and no model download, so the bot always has something to search.
  3. Answer composition: the answer is *extracted* from the best chunks -
     an FAQ/Help answer verbatim, or the sentences of a page/tour that best
     match the question - with a source line and tour cards where relevant.
     Nothing is generated, so it can only say what the site's own content says.

If nothing matches well enough, ``answer`` returns None and the caller falls
back to its scripted replies.
"""

from __future__ import annotations

import html
import logging
import math
import re
import threading
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 300
CHUNK_WORDS = 70
TOP_K = 6
# A hit must match at least this share of the question's meaningful terms
# and reach this BM25 score, otherwise we'd rather say "I don't know".
MIN_TERM_COVERAGE = 0.34
MIN_SCORE = 1.0

_STOPWORDS = frozenset(
    "a an and are as at be but by can could do does for from have how i if in into is it its me my of on or our so "
    "that the their them there these they this to us was we what when where which who why will with would you your "
    "please tell about need want know get give show any some more much many".split()
)

def _stem(word: str) -> str:
    if len(word) > 4:
        for suffix, repl in (("ies", "y"), ("ing", ""), ("ed", ""), ("es", ""), ("s", "")):
            if word.endswith(suffix) and len(word) - len(suffix) >= 3:
                return word[: -len(suffix)] + repl
    return word


def tokenize(text: str) -> list[str]:
    return [_stem(w) for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if w not in _STOPWORDS and len(w) > 1]


def _plain(text: str | None) -> str:
    """CMS content may be HTML; strip it down to readable text."""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text or "", flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>|</p>|</li>|</h\d>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"[ \t\r\f\v]+", " ", text).strip()


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip(" -•\t") for p in parts if p and len(p.strip()) > 2]


@dataclass
class Chunk:
    doc_type: str  # faq | help | page | tour
    doc_id: int
    title: str
    text: str
    url: str | None = None
    # what a FAQ/Help hit answers with verbatim (the question side is only for matching)
    answer: str | None = None
    tokens: Counter = field(default_factory=Counter)
    length: int = 0


class _Index:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self.doc_freq: dict[str, int] = defaultdict(int)
        for chunk in chunks:
            for term in chunk.tokens:
                self.doc_freq[term] += 1
        self.avg_len = (sum(c.length for c in chunks) / len(chunks)) if chunks else 0.0
        self.built_at = time.monotonic()

    def idf(self, term: str) -> float:
        n = len(self.chunks)
        df = self.doc_freq.get(term, 0)
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def score(self, query_terms: list[str]) -> list[tuple[float, Chunk, int]]:
        k1, b = 1.5, 0.75
        results = []
        for chunk in self.chunks:
            total, matched = 0.0, 0
            for term in set(query_terms):
                tf = chunk.tokens.get(term, 0)
                if not tf:
                    continue
                matched += 1
                denom = tf + k1 * (1 - b + b * (chunk.length / (self.avg_len or 1)))
                total += self.idf(term) * (tf * (k1 + 1)) / denom
            if total > 0:
                results.append((total, chunk, matched))
        results.sort(key=lambda r: r[0], reverse=True)
        return results


_index: _Index | None = None
_index_lock = threading.Lock()


def invalidate() -> None:
    global _index
    _index = None


def _make_chunk(doc_type, doc_id, title, text, url=None, answer=None) -> Chunk:
    tokens = Counter(tokenize(f"{title} {title} {text}"))  # title counts double
    return Chunk(doc_type, doc_id, title, text, url, answer, tokens, sum(tokens.values()))


def _split_words(text: str, size: int = CHUNK_WORDS) -> list[str]:
    """Group sentences into ~size-word chunks so long pages score per passage."""
    chunks, current, count = [], [], 0
    for sentence in _sentences(text):
        words = len(sentence.split())
        if current and count + words > size:
            chunks.append(" ".join(current))
            current, count = [], 0
        current.append(sentence)
        count += words
    if current:
        chunks.append(" ".join(current))
    return chunks


def _build_index(db: Session) -> _Index:
    from app.models.chatbot import ChatFAQ
    from app.models.cms import Tour
    from app.models.website_cms import CmsPage, HelpCentreArticle

    chunks: list[Chunk] = []

    seen_faq_questions: set[str] = set()
    for faq in (  # noqa: E712
        db.query(ChatFAQ)
        .filter(ChatFAQ.is_active == True)
        .order_by(ChatFAQ.sort_order, ChatFAQ.id.asc())
        .all()
    ):
        faq_key = " ".join((faq.question or "").lower().split())
        if not faq_key or faq_key in seen_faq_questions:
            continue
        seen_faq_questions.add(faq_key)
        chunks.append(_make_chunk("faq", faq.id, faq.question, f"{faq.question} {faq.answer} {faq.category or ''}", answer=faq.answer))

    for art in db.query(HelpCentreArticle).filter(HelpCentreArticle.is_active == True).all():  # noqa: E712
        chunks.append(_make_chunk("help", art.id, art.question, f"{art.question} {art.answer} {art.category or ''}", "/help-centre", answer=_plain(art.answer)))

    for page in db.query(CmsPage).filter(CmsPage.status == "published").all():
        body = _plain(page.content)
        for piece in _split_words(body) or []:
            chunks.append(_make_chunk("page", page.id, page.title, piece, f"/{page.slug}"))

    for tour in db.query(Tour).filter(Tour.status == "published").all():
        facts = " ".join(filter(None, [
            f"Starts in {tour.start_location}." if tour.start_location else "",
            f"Ends in {tour.finish_location}." if tour.finish_location else "",
            f"{tour.number_of_days}-day tour." if tour.number_of_days else "",
            f"Starting from {tour.currency} {tour.price_start_per_person:,.0f} per person." if tour.price_start_per_person else "",
        ]))
        body = " ".join(filter(None, [_plain(tour.subtitle), _plain(tour.short_description), _plain(tour.long_description), facts]))
        country = getattr(tour, "country", None)
        tour_url = (
            f"/tours/{country.slug}/{tour.slug}"
            if country and country.slug and tour.slug
            else f"/tours/{tour.id}"
        )
        for piece in _split_words(body) or [tour.title]:
            chunks.append(_make_chunk("tour", tour.id, tour.title, piece, tour_url))

    logger.info("Chatbot RAG index built: %d chunks", len(chunks))
    return _Index(chunks)


def _get_index(db: Session) -> _Index:
    global _index
    idx = _index
    if idx is not None and time.monotonic() - idx.built_at < CACHE_TTL_SECONDS:
        return idx
    with _index_lock:
        if _index is None or time.monotonic() - _index.built_at >= CACHE_TTL_SECONDS:
            _index = _build_index(db)
        return _index


@dataclass
class Hit:
    chunk: Chunk
    score: float
    coverage: float


def _semantic_ranks(db: Session, query: str) -> dict[tuple[str, int], int]:
    """Rank of each (type, id) in the vector index, if one has been built."""
    try:
        from app.models.chatbot import ChatEmbedding
        if db.query(ChatEmbedding.id).first() is None:
            return {}
        from app.services import rag
        hits = rag.semantic_search(db, query, ["faq", "tour", "help", "page"], top_k=8, min_score=0.4)
    except Exception:
        logger.debug("Semantic search unavailable; using keyword retrieval only", exc_info=True)
        return {}
    return {(h["source_type"], h["source_id"]): rank for rank, h in enumerate(hits)}


def retrieve(db: Session, query: str, page_tour_id: int | None = None) -> list[Hit]:
    terms = tokenize(query)
    if not terms:
        return []
    idx = _get_index(db)
    scored = idx.score(terms)
    sem = _semantic_ranks(db, query)

    fused: dict[int, tuple[float, Chunk, float]] = {}
    for rank, (score, chunk, matched) in enumerate(scored[:40]):
        coverage = matched / len(set(terms))
        rrf = 1.0 / (60 + rank)
        if (chunk.doc_type, chunk.doc_id) in sem:
            rrf += 1.0 / (60 + sem[(chunk.doc_type, chunk.doc_id)])
        boost = 1.6 if page_tour_id and chunk.doc_type == "tour" and chunk.doc_id == page_tour_id else 1.0
        fused[id(chunk)] = (rrf * boost, chunk, coverage)
    # Vector-only matches (no shared keywords, e.g. a paraphrase) still get a shot.
    seen_docs = {(c.doc_type, c.doc_id) for _, c, _ in fused.values()}
    for (dtype, did), rank in sem.items():
        if (dtype, did) in seen_docs:
            continue
        chunk = next((c for c in idx.chunks if c.doc_type == dtype and c.doc_id == did), None)
        if chunk:
            fused[id(chunk)] = (1.0 / (60 + rank), chunk, MIN_TERM_COVERAGE)

    ordered = sorted(fused.values(), key=lambda v: v[0], reverse=True)
    raw = {id(c): s for s, c, _ in scored}
    hits = [Hit(chunk, raw.get(id(chunk), MIN_SCORE), cov) for _, chunk, cov in ordered]
    return hits[:TOP_K]


def _best_sentences(text: str, query_terms: set[str], limit: int = 2) -> str:
    sentences = _sentences(text)
    ranked = sorted(
        range(len(sentences)),
        key=lambda i: len(query_terms & set(tokenize(sentences[i]))),
        reverse=True,
    )
    chosen = sorted(i for i in ranked[:limit] if query_terms & set(tokenize(sentences[i])))
    if not chosen:
        chosen = [0] if sentences else []
    return " ".join(sentences[i] for i in chosen)


def answer(db: Session, query: str, page_tour_id: int | None = None) -> dict | None:
    """Return {"text": str, "tour_ids": [int]} or None when nothing relevant was found."""
    hits = retrieve(db, query, page_tour_id)
    if not hits:
        return None
    top = hits[0]
    if top.score < MIN_SCORE or top.coverage < MIN_TERM_COVERAGE:
        return None

    query_terms = set(tokenize(query))
    chunk = top.chunk
    tour_ids: list[int] = []
    for h in hits:
        if h.chunk.doc_type == "tour" and h.chunk.doc_id not in tour_ids and h.coverage >= MIN_TERM_COVERAGE:
            tour_ids.append(h.chunk.doc_id)

    if chunk.doc_type in ("faq", "help"):
        text = chunk.answer or chunk.text
        related = next((h.chunk for h in hits[1:] if h.chunk.doc_type in ("faq", "help") and h.chunk.doc_id != chunk.doc_id and h.coverage >= MIN_TERM_COVERAGE), None)
        if related:
            text += f"\n\nYou might also want to know: {related.title}"
        if chunk.doc_type == "help":
            text += "\n\nSource: Help Centre"
    elif chunk.doc_type == "page":
        text = f"{_best_sentences(chunk.text, query_terms, 3)}\n\nSource: {chunk.title} ({chunk.url})"
    else:  # tour
        text = f"{chunk.title}: {_best_sentences(chunk.text, query_terms, 2)}"
        if tour_ids:
            text += "\n\nHere are the matching tours - tap one to see details or start booking."

    if chunk.doc_type != "tour":
        tour_ids = [t for t in tour_ids if _wants_tours(query)]
    return {"text": text.strip(), "tour_ids": tour_ids[:4]}


_TOUR_WORDS = ("tour", "trip", "package", "itinerary", "holiday", "vacation", "travel to", "visit", "things to do")


def _wants_tours(query: str) -> bool:
    q = query.lower()
    return any(w in q for w in _TOUR_WORDS)
