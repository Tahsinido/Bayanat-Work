"""Stored semantic vector for a bulletin.

The vector is kept as raw float32 bytes rather than an array column so the
feature works on a stock PostgreSQL: pgvector is not installed here (the image
ships PostGIS only). Search loads the vectors into a numpy matrix and scores
them in process, which is comfortably fast into the low hundreds of thousands
of bulletins. Moving to pgvector later only changes this storage layer.
"""

from typing import Any, Optional

from enferno.extensions import db
from enferno.utils.base import BaseMixin
from enferno.utils.logging_utils import get_logger

logger = get_logger()


class BulletinEmbedding(db.Model, BaseMixin):
    """SQL Alchemy model for a bulletin's semantic embedding."""

    __tablename__ = "bulletin_embedding"
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    bulletin_id = db.Column(
        db.Integer,
        db.ForeignKey("bulletin.id", ondelete="CASCADE"),
        index=True,
        unique=True,
        nullable=False,
    )
    bulletin = db.relationship("Bulletin", backref=db.backref("embedding", uselist=False))

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
            "model": self.model,
            "dim": self.dim,
            "content_hash": self.content_hash,
        }

    def __repr__(self) -> str:
        return f"<BulletinEmbedding bulletin={self.bulletin_id} model={self.model}>"
