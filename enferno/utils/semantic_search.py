"""Meaning-based bulletin search, running entirely on this server.

The model is baked into the image at build time and loaded from disk with the
transformers offline flags set, so no query text and no bulletin content is
ever sent anywhere. If the optional `semantic` extra was not installed the
module degrades quietly: `is_available()` returns False and the API reports
that semantic search is switched off rather than erroring.

Storage is a plain bytea column (see BulletinEmbedding) because pgvector is not
present in the PostGIS image this project ships. Vectors are L2-normalised at
write time, so scoring is a single matrix-vector product.

Retrieval is deliberately narrow: a query is embedded once, compared against the
stored vectors, cut at a similarity threshold, and truncated to the best few.
Nothing is re-embedded per result at request time except the short passages used
to explain a match, and those are batched into one call.
"""

from __future__ import annotations

import hashlib
import os
import re
import threading
from collections import OrderedDict
from typing import Any, Optional

import numpy as np

from enferno.utils.logging_utils import get_logger
from enferno.utils.search_snippets import strip_html

logger = get_logger()

DEFAULT_MODEL_PATH = os.environ.get("SEMANTIC_MODEL_PATH", "/app/models/semantic")

# Relevance floor and page size. Both are overridable per deployment through
# app settings (config.json / the admin settings screen) or the matching
# environment variable -- see settings.Config.
DEFAULT_SIMILARITY_THRESHOLD = 0.65
DEFAULT_MAX_RESULTS = 20

# Restricted bulletins are dropped *after* retrieval, so asking the index for
# exactly max_results would return a short page. Over-fetch, but bound it: the
# extra candidates cost one dot product each and nothing more.
CANDIDATE_MULTIPLIER = 5
MAX_CANDIDATES = 500

# Queries repeat constantly (re-search, refine one word, toggle a filter) and a
# query vector is ~1.5 KB, so keeping the last few skips the encode entirely.
QUERY_CACHE_SIZE = 256

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

_query_cache: "OrderedDict[str, np.ndarray]" = OrderedDict()
_query_cache_lock = threading.Lock()


# --------------------------------------------------------------------------
# Tunables
# --------------------------------------------------------------------------


def _setting(key: str, default, cast):
    """Read a tunable from app settings, then the environment, then the default.

    Kept tolerant on purpose: a malformed value in config.json must not take
    search down, so it is logged and the default stands.
    """
    value = None
    try:
        from enferno.settings import Config

        value = Config.get(key, None)
    except Exception:
        value = None

    if value is None:
        value = os.environ.get(key)
    if value is None or value == "":
        return default

    try:
        return cast(value)
    except (TypeError, ValueError):
        logger.warning(f"Invalid {key}={value!r}, falling back to {default}")
        return default


def similarity_threshold() -> float:
    """Minimum cosine similarity a bulletin must reach to be returned."""
    value = _setting("SEMANTIC_SEARCH_THRESHOLD", DEFAULT_SIMILARITY_THRESHOLD, float)
    return min(max(value, 0.0), 1.0)


def max_results() -> int:
    """Most bulletins a single semantic search may return."""
    return max(1, _setting("SEMANTIC_SEARCH_MAX_RESULTS", DEFAULT_MAX_RESULTS, int))


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


def encode_query(query: str) -> np.ndarray:
    """Embed a search query, at most once per distinct query.

    Encoding is the single most expensive step of a search, and it does not
    depend on how many bulletins are indexed. Callers that need the vector for
    more than retrieval (passage selection, for instance) should take it from
    here rather than encoding the query a second time.
    """
    key = (query or "").strip()
    with _query_cache_lock:
        cached = _query_cache.get(key)
        if cached is not None:
            _query_cache.move_to_end(key)
            return cached

    vector = encode([key])[0]

    with _query_cache_lock:
        _query_cache[key] = vector
        _query_cache.move_to_end(key)
        while len(_query_cache) > QUERY_CACHE_SIZE:
            _query_cache.popitem(last=False)
    return vector


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

    def search(
        self, query_vector: np.ndarray, limit: int, min_score: float = 0.0
    ) -> list[tuple[int, float]]:
        """Return (bulletin_id, similarity) pairs above `min_score`, best first.

        One dot product covers the whole index; the threshold then cuts it down
        before any sorting happens, so the cost of ordering scales with the
        number of *relevant* bulletins rather than the number indexed.
        """
        if self.matrix.size == 0 or limit <= 0:
            return []

        # Vectors are normalised, so the dot product is the cosine.
        scores = self.matrix @ query_vector

        if min_score > 0.0:
            keep = np.flatnonzero(scores >= min_score)
            if keep.size == 0:
                return []
            subset = scores[keep]
        else:
            keep = None
            subset = scores

        take = min(limit, subset.shape[0])
        if take < subset.shape[0]:
            # Partial selection: O(n) instead of a full O(n log n) sort.
            top = np.argpartition(-subset, take - 1)[:take]
        else:
            top = np.arange(subset.shape[0])
        top = top[np.argsort(-subset[top])]

        rows = top if keep is None else keep[top]
        return [(int(self.ids[r]), float(scores[r])) for r in rows]


_index = _Index()


def search_vector(
    query_vector: np.ndarray, limit: Optional[int] = None, min_score: Optional[float] = None
) -> list[tuple[int, float]]:
    """Closest bulletins to an already-embedded query, best first.

    Split out from `search` so a caller that also needs the query vector can
    embed once and pass it in.
    """
    if limit is None:
        limit = max_results()
    if min_score is None:
        min_score = similarity_threshold()
    _index.load()
    return _index.search(query_vector, limit, min_score)


def search(
    query: str, limit: Optional[int] = None, min_score: Optional[float] = None
) -> list[tuple[int, float]]:
    """Embed the query and return the closest bulletins above the threshold."""
    if not query or not query.strip():
        return []
    return search_vector(encode_query(query), limit, min_score)


def invalidate_index() -> None:
    """Force the next search to reload from the table."""
    _index.stamp = None


def indexed_count() -> int:
    """How many bulletins the loaded index holds."""
    return int(_index.matrix.shape[0]) if _index.matrix.size else 0


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


def best_passages(
    texts: list[str],
    query_vector: np.ndarray,
    max_sentences: int = 12,
    max_total: int = 240,
) -> list[Optional[str]]:
    """The sentence that best explains each match, in a single embedding pass.

    Embedding is dominated by per-call overhead, so one call for every result on
    the page beats one call per result. Two caps keep the worst case bounded
    regardless of how long the documents are: `max_sentences` per document and
    `max_total` across the whole page.

    Returns one entry per input text, None where nothing was long enough to
    quote.
    """
    spans: list[tuple[int, int]] = []
    sentences: list[str] = []
    budget = max_total

    for text in texts:
        picked: list[str] = []
        if budget > 0 and text:
            picked = [s.strip() for s in _SENTENCE_SPLIT.split(text) if len(s.strip()) > 20]
            picked = picked[: min(max_sentences, budget)]
        spans.append((len(sentences), len(picked)))
        sentences.extend(picked)
        budget -= len(picked)

    if not sentences:
        return [None] * len(texts)

    scores = encode(sentences) @ query_vector

    out: list[Optional[str]] = []
    for start, count in spans:
        if count == 0:
            out.append(None)
            continue
        out.append(sentences[start + int(np.argmax(scores[start : start + count]))])
    return out


def best_passage(text: str, query_vector: np.ndarray, max_sentences: int = 12) -> Optional[str]:
    """The sentence that best explains why a single document matched."""
    return best_passages([text], query_vector, max_sentences=max_sentences)[0]


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
