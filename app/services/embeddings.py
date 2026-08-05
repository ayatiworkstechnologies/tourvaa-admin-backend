"""Local text embeddings for RAG retrieval.

Uses fastembed (ONNX runtime, no torch/GPU required) to keep this dependency
light -- there is no Anthropic embeddings endpoint, and adding a hosted
embeddings provider or a dedicated vector DB is not worth it for a single
tour catalog + FAQ set. Vectors are consumed by app/services/rag.py and
stored in the chat_embeddings table (see app/models/chatbot.py).
"""

import logging
import threading

from app.config import settings

logger = logging.getLogger(__name__)

# BAAI/bge models are trained with an asymmetric instruction: prefix the
# *query* at search time, leave passages (tours/FAQs) unprefixed at index time.
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

_model = None
_model_lock = threading.Lock()


def _get_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from fastembed import TextEmbedding

                model_name = settings.CHATBOT_EMBEDDING_MODEL or "BAAI/bge-small-en-v1.5"
                logger.info("Loading embedding model %s", model_name)
                _model = TextEmbedding(model_name=model_name)
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed passages (tours, FAQs) for indexing. No instruction prefix."""
    if not texts:
        return []
    model = _get_model()
    return [vector.tolist() for vector in model.embed(texts)]


def embed_query(text: str) -> list[float]:
    """Embed a user's chat message for retrieval."""
    return embed_texts([QUERY_INSTRUCTION + text])[0]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
