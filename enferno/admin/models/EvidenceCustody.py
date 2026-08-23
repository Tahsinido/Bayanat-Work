"""Chain of custody: one row per custody event, append-only.

Custody is a sequence, not a state. Recording it as columns on the evidence
record would mean each transfer overwrote the last, which is precisely what the
specification forbids -- so every collection, receipt, transfer and storage
change is its own immutable row here, and the chain is the rows in time order.

There is deliberately no update path. The API exposes create and list only: a
mistake is corrected by appending a correcting entry, not by editing history.
That is the same reason a paper custody form is initialled rather than erased.
"""

from typing import Any

from enferno.extensions import db
from enferno.utils.base import BaseMixin
from enferno.utils.date_helper import DateHelper
from enferno.utils.logging_utils import get_logger

logger = get_logger()


class EvidenceCustody(db.Model, BaseMixin):
    """SQL Alchemy model for a single chain-of-custody event."""

    __tablename__ = "evidence_custody"
    __table_args__ = {"extend_existing": True}

    # What kind of custody event this row records.
    ACTION_COLLECTED = "Collected"
    ACTION_RECEIVED = "Received"
    ACTION_TRANSFERRED = "Transferred"
    ACTION_STORED = "Stored"
    ACTION_RETURNED = "Returned"
    ACTION_ACCESSED = "Accessed"
    ACTION_CORRECTION = "Correction"

    ACTIONS = [
        ACTION_COLLECTED,
        ACTION_RECEIVED,
        ACTION_TRANSFERRED,
        ACTION_STORED,
        ACTION_RETURNED,
        ACTION_ACCESSED,
        ACTION_CORRECTION,
    ]

    id = db.Column(db.Integer, primary_key=True)

    evidence_id = db.Column(
        db.Integer,
        db.ForeignKey("evidence.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    evidence = db.relationship("Evidence", backref=db.backref("custody", lazy="joined"))

    action = db.Column(db.String, nullable=False, index=True)

    # Who handled the evidence at this step. Free text because the person is
    # frequently outside Bayanat -- a field partner, a courier, a lab.
    handled_by = db.Column(db.String)
    # The Bayanat user who recorded the entry, which is not necessarily the
    # person who handled the item.
    recorded_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    recorded_by = db.relationship("User", foreign_keys=[recorded_by_id])

    # When the custody event happened, as opposed to when it was typed in
    # (created_at). Backdating a paper form is normal and must be representable.
    occurred_at = db.Column(db.DateTime, index=True)

    location = db.Column(db.String)
    received_from = db.Column(db.String)
    transferred_to = db.Column(db.String)
    purpose = db.Column(db.Text)
    storage_location = db.Column(db.String)
    condition = db.Column(db.Text)

    # Reference to the paper or scanned custody form.
    reference = db.Column(db.String)
    # The supporting custody document itself, held as Media like any other file.
    document_media_id = db.Column(db.Integer, db.ForeignKey("media.id", ondelete="SET NULL"))
    document_media = db.relationship("Media", foreign_keys=[document_media_id])

    notes = db.Column(db.Text)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "class": "evidence_custody",
            "evidence_id": self.evidence_id,
            "action": self.action,
            "handled_by": self.handled_by,
            "recorded_by": self.recorded_by.to_compact() if self.recorded_by else None,
            "occurred_at": DateHelper.serialize_datetime(self.occurred_at),
            "location": self.location,
            "received_from": self.received_from,
            "transferred_to": self.transferred_to,
            "purpose": self.purpose,
            "storage_location": self.storage_location,
            "condition": self.condition,
            "reference": self.reference,
            "document_media": (
                {
                    "id": self.document_media.id,
                    "filename": self.document_media.media_file,
                    "title": self.document_media.title,
                }
                if self.document_media
                else None
            ),
            "notes": self.notes,
            "created_at": DateHelper.serialize_datetime(self.created_at),
        }

    def to_mini(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "class": "evidence_custody",
            "evidence_id": self.evidence_id,
            "action": self.action,
        }

    def from_json(self, json: dict[str, Any]) -> "EvidenceCustody":
        self.action = json.get("action")
        self.handled_by = json.get("handled_by")
        self.location = json.get("location")
        self.received_from = json.get("received_from")
        self.transferred_to = json.get("transferred_to")
        self.purpose = json.get("purpose")
        self.storage_location = json.get("storage_location")
        self.condition = json.get("condition")
        self.reference = json.get("reference")
        self.notes = json.get("notes")

        if json.get("occurred_at"):
            self.occurred_at = DateHelper.parse_datetime(json["occurred_at"])

        document = json.get("document_media")
        self.document_media_id = document.get("id") if document else None
        return self

    def __repr__(self) -> str:
        return f"<EvidenceCustody {self.action} evidence={self.evidence_id}>"
