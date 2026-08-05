"""Meaning-based bulletin search, running entirely on this server.

The model is baked into the image at build time and loaded from disk with the
transformers offline flags set, so no query text and no bulletin content is
ever sent anywhere. If the optional `semantic` extra was not installed the
module degrades quietly: `is_available()` returns False and the API reports
that semantic search is switched off rather than erroring.

Storage is a plain bytea column (see BulletinEmbedding) because pgvector is not
present in the PostGIS image this project ships. Vectors are L2-normalised at
write time, so scoring is a single matrix-vector product.
"""

from __future__ import annotations

import hashlib
import os
import re
import threading
from typing import Any, Iterable, Optional

import numpy as np

from enferno.utils.logging_utils import get_logger
from enferno.utils.search_snippets import strip_html

logger = get_logger()

DEFAULT_MODEL_PATH = os.environ.get("SEMANTIC_MODEL_PATH", "/app/models/semantic")

# Sentence splitter covering Latin and Arabic terminators.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?؟۔])\s+|\n+")
_WORD = re.compile(r"\w+", re.UNICODE)

# Query words too common to count as evidence in a "why this matched" list.
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "for",
    "from", "had", "has", "have", "he", "her", "his", "i", "in", "is", "it",
    "its", "me", "my", "of", "on", "or", "she", "that", "the", "their",
    "there", "they", "this", "to", "was", "were", "who", "with", "you", "am",
    "been", "here", "have", "years", "year", "old",
}

_model = None
_model_lock = threading.Lock()


def is_available() -> bool:
    """True when the optional dependency and the model files are both present."""
    try:
        import sentence_transformers  # noqa: F401
    except Exception:
        return False
    return os.path.isdir(DEFAULT_MODEL_PATH)


def unavailable_reason() -> Optional[str]:
    """Explain why semantic search cannot run, or None when it can."""
    try:
        import sentence_transformers  # noqa: F401
    except Exception:
        return (
            "The semantic search dependencies are not installed. Rebuild the "
            "image with --build-arg WITH_SEMANTIC=true."
        )
    if not os.path.isdir(DEFAULT_MODEL_PATH):
        return (
            f"The embedding model is missing from {DEFAULT_MODEL_PATH}. Rebuild "
            "the image with --build-arg WITH_SEMANTIC=true."
        )
    return None


def get_model():
    """Load the sentence-transformer once per process.

    Loading costs a few seconds and a few hundred MB, so it is deferred until
    the first semantic query rather than paid at every worker start.
    """
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is None:
            from sentence_transformers import SentenceTransformer

            logger.info(f"Loading semantic model from {DEFAULT_MODEL_PATH}")
            _model = SentenceTransformer(DEFAULT_MODEL_PATH, device="cpu")
            logger.info("Semantic model ready")
    return _model


def model_name() -> str:
    """Identifier stored alongside each vector to detect model changes."""
    return os.path.basename(DEFAULT_MODEL_PATH.rstrip("/")) or "semantic"


def encode(texts: list[str]) -> np.ndarray:
    """Embed texts and return normalised float32 vectors."""
    model = get_model()
    vectors = model.encode(
        texts,
        batch_size=16,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return np.asarray(vectors, dtype=np.float32)


# --------------------------------------------------------------------------
# Turning a bulletin into text
# --------------------------------------------------------------------------


def bulletin_text(bulletin) -> str:
    """Assemble everything searchable about a bulletin into one string.

    Covers the fields the request asks for: titles, description, comments,
    tags, locations, labels, sources, and OCR text extracted from attachments.
    """
    parts: list[str] = []

    def add(value):
        if value:
            text = strip_html(str(value)) if "<" in str(value) else str(value)
            if text.strip():
                parts.append(text.strip())

    add(bulletin.title)
    add(bulletin.title_ar)
    add(bulletin.sjac_title)
    add(bulletin.sjac_title_ar)
    add(bulletin.description)
    add(bulletin.comments)
    add(bulletin.originid)

    if bulletin.tags:
        add(" ".join(bulletin.tags))

    for loc in getattr(bulletin, "locations", None) or []:
        add(getattr(loc, "full_location", None) or getattr(loc, "title", None))
    for label in getattr(bulletin, "labels", None) or []:
        add(getattr(label, "title", None))
    for label in getattr(bulletin, "ver_labels", None) or []:
        add(getattr(label, "title", None))
    for source in getattr(bulletin, "sources", None) or []:
        add(getattr(source, "title", None))
    for event in getattr(bulletin, "events", None) or []:
        add(getattr(event, "title", None))
        add(getattr(event, "comments", None))

    # OCR / transcription text from attached media.
    for media in getattr(bulletin, "medias", None) or []:
        extraction = getattr(media, "extraction", None)
        if extraction is not None:
            add(getattr(extraction, "search_text", None))
        add(getattr(media, "title", None))

    return "\n".join(parts)


def content_hash(text: str) -> str:
    """Stable digest so unchanged bulletins can be skipped on re-index."""
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


# --------------------------------------------------------------------------
# Index
# --------------------------------------------------------------------------


class _Index:
    """In-memory matrix of stored vectors, rebuilt when the table changes."""

    def __init__(self):
        self.ids: np.ndarray = np.empty(0, dtype=np.int64)
        self.matrix: np.ndarray = np.empty((0, 0), dtype=np.float32)
        self.model: Optional[str] = None
        self.stamp: Optional[tuple] = None
        self.lock = threading.Lock()

    def load(self, force: bool = False) -> None:
        from enferno.admin.models import BulletinEmbedding
        from enferno.extensions import db

        current = model_name()
        # (row count, newest update) is enough to notice adds, edits, deletes.
        stamp = db.session.query(
            db.func.count(BulletinEmbedding.id),
            db.func.max(BulletinEmbedding.updated_at),
        ).filter(BulletinEmbedding.model == current).one()

        with self.lock:
            if not force and self.stamp == stamp and self.model == current:
                return

            rows = (
                db.session.query(BulletinEmbedding.bulletin_id, BulletinEmbedding.vector)
                .filter(BulletinEmbedding.model == current)
                .all()
            )
            if rows:
                self.ids = np.array([r[0] for r in rows], dtype=np.int64)
                self.matrix = np.vstack(
                    [np.frombuffer(r[1], dtype=np.float32) for r in rows]
                )
            else:
                self.ids = np.empty(0, dtype=np.int64)
                self.matrix = np.empty((0, 0), dtype=np.float32)
            self.model = current
            self.stamp = stamp
            logger.info(f"Semantic index loaded: {len(self.ids)} bulletins")

    def search(self, query_vector: np.ndarray, limit: int) -> list[tuple[int, float]]:
        """Return (bulletin_id, similarity) pairs, best first."""
        if self.matrix.size == 0:
            return []
        # Vectors are normalised, so the dot product is the cosine.
        scores = self.matrix @ query_vector
        take = min(limit, scores.shape[0])
        top = np.argpartition(-scores, take - 1)[:take]
        top = top[np.argsort(-scores[top])]
        return [(int(self.ids[i]), float(scores[i])) for i in top]


_index = _Index()


def search(query: str, limit: int = 50) -> list[tuple[int, float]]:
    """Embed the query and return the closest bulletins."""
    if not query or not query.strip():
        return []
    _index.load()
    vector = encode([query])[0]
    return _index.search(vector, limit)


def invalidate_index() -> None:
    """Force the next search to reload from the table."""
    _index.stamp = None


# --------------------------------------------------------------------------
# Explaining a match
# --------------------------------------------------------------------------


def query_terms(query: str) -> list[str]:
    """Meaningful words from the query, lowercased and de-duplicated."""
    seen, out = set(), []
    for word in _WORD.findall(query.lower()):
        if len(word) < 2 or word in _STOPWORDS or word in seen:
            continue
        seen.add(word)
        out.append(word)
    return out


def best_passage(text: str, query_vector: np.ndarray, max_sentences: int = 40) -> Optional[str]:
    """The sentence that best explains why a document matched.

    Only the first `max_sentences` are considered, which bounds the cost on
    very long documents.
    """
    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(text) if len(s.strip()) > 20]
    if not sentences:
        return None
    sentences = sentences[:max_sentences]
    vectors = encode(sentences)
    scores = vectors @ query_vector
    return sentences[int(np.argmax(scores))]


def explain(bulletin, text: str, terms: list[str]) -> dict[str, Any]:
    """Ground the match in things actually present on the bulletin.

    Rather than guessing entities with a general-purpose NER model, query words
    are checked against this bulletin's own locations, labels, sources and
    tags. That is both cheaper and more accurate for this data.
    """
    lowered = text.lower()

    keywords = [t for t in terms if t in lowered]

    def names(items, *attrs):
        out = []
        for item in items or []:
            for attr in attrs:
                value = getattr(item, attr, None)
                if value:
                    out.append(str(value))
                    break
        return out

    def matched(values):
        hits = []
        for value in values:
            low = value.lower()
            if any(t in low for t in terms):
                hits.append(value)
        return hits

    return {
        "keywords": keywords,
        "locations": matched(names(getattr(bulletin, "locations", None), "full_location", "title")),
        "labels": matched(names(getattr(bulletin, "labels", None), "title")),
        "sources": matched(names(getattr(bulletin, "sources", None), "title")),
        "tags": matched(list(getattr(bulletin, "tags", None) or [])),
    }
