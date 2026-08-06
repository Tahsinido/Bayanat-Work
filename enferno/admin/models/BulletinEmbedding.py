"""Stored semantic vectors for a bulletin, one row per passage.

The vector is kept as raw float32 bytes rather than an array column so the
feature works on a stock PostgreSQL: pgvector is not installed here (the image
ships PostGIS only). Search loads the vectors into a numpy matrix and scores
them in process, which is comfortably fast into the low hundreds of thousands
of bulletins. Moving to pgvector later only changes this storage layer.

A bulletin owns several rows because the embedding model has a fixed input
window: a single vector per bulletin silently dropped everything past the first
128 tokens, which in practice cut the description short and lost every field
after it. Each row holds one chunk plus the text it came from, so the passage
that explains a match is already known at retrieval time.
"""

from typing import Any

from enferno.extensions import db
from enferno.utils.base import BaseMixin
from enferno.utils.logging_utils import get_logger

logger = get_logger()


class BulletinEmbedding(db.Model, BaseMixin):
    """SQL Alchemy model for a bulletin's semantic embedding."""

    __tablename__ = "bulletin_embedding"
    __table_args__ = (
        db.UniqueConstraint(
            "bulletin_id", "model", "chunk_index", name="uq_bulletin_embedding_chunk"
        ),
        {"extend_existing": True},
    )

    id = db.Column(db.Integer, primary_key=True)
    bulletin_id = db.Column(
        db.Integer,
        db.ForeignKey("bulletin.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    bulletin = db.relationship("Bulletin", backref=db.backref("embeddings", lazy="dynamic"))

    # Position of this passage within the bulletin. Unique per (bulletin,
    # model) so a re-index cannot leave duplicates behind.
    chunk_index = db.Column(db.Integer, nullable=False, server_default="0")

    # The passage this vector was built from, kept so a search result can show
    # why it matched without re-reading and re-embedding the bulletin.
    chunk_text = db.Column(db.Text, nullable=True)

    # Which model produced this vector. A change here invalidates the row:
    # vectors from different models are not comparable.
    model = db.Column(db.String, nullable=False, index=True)
    dim = db.Column(db.Integer, nullable=False)

    # float32 little-endian, `dim` values. Already L2-normalised, so cosine
    # similarity is a plain dot product.
    vector = db.Column(db.LargeBinary, nullable=False)

    # Hash of the text that produced the vector, so a re-index can skip
    # bulletins whose searchable content has not changed.
    content_hash = db.Column(db.String, nullable=False, index=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "bulletin_id": self.bulletin_id,
            "chunk_index": self.chunk_index,
            "model": self.model,
            "dim": self.dim,
            "content_hash": self.content_hash,
        }

    def __repr__(self) -> str:
        return (
            f"<BulletinEmbedding bulletin={self.bulletin_id} "
            f"chunk={self.chunk_index} model={self.model}>"
        )
