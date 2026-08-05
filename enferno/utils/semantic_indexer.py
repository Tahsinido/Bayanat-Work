"""Keeping bulletin embeddings in step with bulletin content."""

from __future__ import annotations

from typing import Iterable, Optional

from enferno.extensions import db
from enferno.utils.logging_utils import get_logger
from enferno.utils import semantic_search as ss

logger = get_logger()


def index_bulletins(bulletins: Iterable, force: bool = False) -> tuple[int, int]:
    """Embed and store vectors for the given bulletins.

    Returns (written, skipped). A bulletin is skipped when its searchable text
    is unchanged since the stored vector was made, which makes re-running the
    backfill cheap.
    """
    from enferno.admin.models import BulletinEmbedding

    model = ss.model_name()
    pending, rows = [], []

    for bulletin in bulletins:
        text = ss.bulletin_text(bulletin)
        if not text.strip():
            continue
        digest = ss.content_hash(text)
        existing = BulletinEmbedding.query.filter_by(bulletin_id=bulletin.id).first()
        if (
            existing
            and not force
            and existing.content_hash == digest
            and existing.model == model
        ):
            continue
        pending.append(text)
        rows.append((bulletin.id, digest, existing))

    if not pending:
        return 0, 0

    vectors = ss.encode(pending)

    written = 0
    for (bulletin_id, digest, existing), vector in zip(rows, vectors):
        record = existing or BulletinEmbedding(bulletin_id=bulletin_id)
        record.model = model
        record.dim = int(vector.shape[0])
        record.vector = vector.astype("float32").tobytes()
        record.content_hash = digest
        db.session.add(record)
        written += 1

    db.session.commit()
    ss.invalidate_index()
    return written, 0


def index_bulletin(bulletin, force: bool = False) -> bool:
    """Index a single bulletin, swallowing errors.

    Called after a bulletin is saved. Indexing must never be the reason a save
    appears to fail, so problems are logged and reported as False.
    """
    if not ss.is_available():
        return False
    try:
        written, _ = index_bulletins([bulletin], force=force)
        return bool(written)
    except Exception as e:
        logger.error(f"Failed to index bulletin {getattr(bulletin, 'id', '?')}: {e}")
        db.session.rollback()
        return False


def reindex_all(batch_size: int = 64, force: bool = False) -> dict:
    """Rebuild embeddings for every bulletin, in batches."""
    from enferno.admin.models import Bulletin

    total = db.session.query(db.func.count(Bulletin.id)).scalar() or 0
    written = 0
    processed = 0

    query = Bulletin.query.order_by(Bulletin.id)
    for offset in range(0, total, batch_size):
        batch = query.limit(batch_size).offset(offset).all()
        if not batch:
            break
        count, _ = index_bulletins(batch, force=force)
        written += count
        processed += len(batch)
        logger.info(f"Semantic index: {processed}/{total} processed, {written} written")

    ss.invalidate_index()
    return {"total": total, "processed": processed, "written": written}
