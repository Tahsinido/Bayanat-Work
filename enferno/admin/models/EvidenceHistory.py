"""Field-level revision history for evidence records.

Mirrors BulletinHistory: each save writes a full JSON snapshot, so any past
state of an evidence record can be reconstructed and compared. Custody events
are a separate, append-only concern (see EvidenceCustody) -- this table covers
edits to the descriptive metadata.

Snapshots exclude attached media, which have their own lifecycle and their own
identifiers; a revision records what the record said, not what was attached at
the time.
"""

import json
from typing import Any

from sqlalchemy import JSON

from enferno.admin.models.utils import check_history_access
from enferno.extensions import db
from enferno.utils.base import BaseMixin
from enferno.utils.date_helper import DateHelper
from enferno.utils.logging_utils import get_logger

logger = get_logger()


class EvidenceHistory(db.Model, BaseMixin):
    """SQL Alchemy model for evidence revisions."""

    __tablename__ = "evidence_history"
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    evidence_id = db.Column(
        db.Integer, db.ForeignKey("evidence.id", ondelete="CASCADE"), index=True
    )
    evidence = db.relationship(
        "Evidence",
        backref=db.backref("history", order_by="EvidenceHistory.updated_at"),
        foreign_keys=[evidence_id],
    )
    data = db.Column(JSON)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    user = db.relationship("User", backref="evidence_revisions", foreign_keys=[user_id])

    @property
    def restricted_data(self):
        """The subset visible to users without full-history permission.

        Deliberately narrow: an evidence record's description and source can
        themselves be sensitive, so a user who may not see the full history sees
        only the workflow trail.
        """
        return {
            "status": self.data.get("status") if self.data else None,
            "confidentiality": self.data.get("confidentiality") if self.data else None,
            "notes": self.data.get("notes") if self.data else None,
        }

    @check_history_access
    def to_dict(self, full=False) -> dict[str, Any]:
        """Return a dictionary representation of the evidence revision."""
        return {
            "id": self.id,
            "data": self.data if full else self.restricted_data,
            "created_at": DateHelper.serialize_datetime(self.created_at),
            "user": self.user.to_compact() if self.user else None,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)

    def __repr__(self):
        return "<EvidenceHistory {} -- Target {}>".format(self.id, self.evidence_id)
