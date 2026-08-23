"""An evidence record: the metadata describing an item of evidence.

The distinction the specification asks for is kept structural rather than
conventional: this model holds *metadata about* the evidence, while the evidence
itself -- the file, photograph, recording, scan -- lives in Media rows pointing
back here via Media.evidence_id. Nothing about the file content is duplicated
into these columns.

Relationships reuse Bayanat's existing vocabulary (Bulletin, Actor, Location,
Event, Source) instead of carrying parallel free-text copies, so evidence filed
against a location is searchable alongside every other record at that location.

Chain of custody is deliberately NOT a column here. Custody is a sequence of
events, and the specification requires that transfers not be silently
overwritten, so it lives in EvidenceCustody as append-only rows.

FIELD NAMING IS A DRAFT. These names were derived from the summary list in the
request, not from the authoritative Evidence document, which was not available.
Every column below is marked in the module docstring of the migration; expect to
reconcile terminology once that document is supplied.
"""

from typing import Any, Optional

from enferno.extensions import db
from enferno.utils.base import BaseMixin
from enferno.utils.date_helper import DateHelper
from enferno.utils.logging_utils import get_logger
from enferno.admin.models.tables import (
    evidence_actors,
    evidence_bulletins,
    evidence_events,
    evidence_locations,
    evidence_related,
    evidence_roles,
    evidence_sources,
)

logger = get_logger()


class Evidence(db.Model, BaseMixin):
    """SQL Alchemy model for an evidence record."""

    __tablename__ = "evidence"
    __table_args__ = {"extend_existing": True}

    # Status values. Kept as a plain string column with these constants rather
    # than a DB enum, matching how Bulletin handles status: a deployment can add
    # a workflow state without a migration.
    STATUS_DRAFT = "Draft"
    STATUS_UNDER_REVIEW = "Under Review"
    STATUS_VERIFIED = "Verified"
    STATUS_ARCHIVED = "Archived"

    # Sensitivity classification. Names follow the request's "confidentiality /
    # sensitivity classification" field.
    CONFIDENTIALITY_PUBLIC = "Public"
    CONFIDENTIALITY_INTERNAL = "Internal"
    CONFIDENTIALITY_RESTRICTED = "Restricted"
    CONFIDENTIALITY_SECRET = "Highly Sensitive"

    id = db.Column(db.Integer, primary_key=True)

    # Human-readable unique identifier (EVD-000123). Separate from the primary
    # key so it can be quoted in correspondence and on custody forms, and so it
    # never depends on the original filename (requirement 12).
    evidence_number = db.Column(db.String, unique=True, index=True, nullable=False)

    # The case this exhibit belongs to, as the team's own reference rather than
    # anything Bayanat generates. Entered by hand and not unique: several
    # exhibits routinely share one case. Indexed because it is the identifier
    # people actually search by.
    case_code = db.Column(db.String, index=True)

    # --- description of the evidence -------------------------------------
    evidence_type = db.Column(db.String, index=True)
    description = db.Column(db.Text)
    content_summary = db.Column(db.Text)

    # --- source ----------------------------------------------------------
    # Free text alongside the structured `sources` relation: a source is often
    # described in prose before it is worth creating a Source record for.
    source_information = db.Column(db.Text)
    ownership_information = db.Column(db.Text)

    # --- dates -----------------------------------------------------------
    # When the evidence itself dates from, as opposed to when it reached us.
    evidence_date = db.Column(db.DateTime, index=True)
    date_collected = db.Column(db.DateTime, index=True)

    # --- collection ------------------------------------------------------
    collection_information = db.Column(db.Text)
    # Free text because the collector is frequently not a Bayanat user -- a
    # field partner, a relative, a local official.
    collector = db.Column(db.String)
    collected_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    collected_by = db.relationship("User", foreign_keys=[collected_by_id])
    # Where the evidence was collected or obtained, distinct from the locations
    # the evidence is *about* (the `locations` relation below).
    collection_location_id = db.Column(db.Integer, db.ForeignKey("location.id"))
    collection_location = db.relationship("Location", foreign_keys=[collection_location_id])

    # --- consent ---------------------------------------------------------
    consent_status = db.Column(db.String)
    consent_information = db.Column(db.Text)

    # --- assessment ------------------------------------------------------
    relevance = db.Column(db.Text)
    verification_information = db.Column(db.Text)

    # --- classification and workflow -------------------------------------
    confidentiality = db.Column(db.String, index=True)
    status = db.Column(db.String, index=True, default=STATUS_DRAFT)
    notes = db.Column(db.Text)

    # --- ownership within Bayanat ----------------------------------------
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    user = db.relationship("User", foreign_keys=[user_id])
    assigned_to_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    assigned_to = db.relationship("User", foreign_keys=[assigned_to_id])

    # --- relationships ---------------------------------------------------
    # Access-control roles, exactly as Bulletin uses them: an empty set means
    # unrestricted, any role means only holders of that role may access.
    roles = db.relationship(
        "Role", secondary=evidence_roles, backref=db.backref("evidence", lazy="dynamic")
    )
    bulletins = db.relationship(
        "Bulletin", secondary=evidence_bulletins, backref=db.backref("evidence", lazy="dynamic")
    )
    actors = db.relationship(
        "Actor", secondary=evidence_actors, backref=db.backref("evidence", lazy="dynamic")
    )
    locations = db.relationship(
        "Location", secondary=evidence_locations, backref=db.backref("evidence", lazy="dynamic")
    )
    events = db.relationship(
        "Event", secondary=evidence_events, backref=db.backref("evidence", lazy="dynamic")
    )
    sources = db.relationship(
        "Source", secondary=evidence_sources, backref=db.backref("evidence", lazy="dynamic")
    )
    # "Related records": other evidence items. primaryjoin/secondaryjoin are
    # spelled out because both sides point at the same table.
    related_evidence = db.relationship(
        "Evidence",
        secondary=evidence_related,
        primaryjoin=id == evidence_related.c.evidence_id,
        secondaryjoin=id == evidence_related.c.related_evidence_id,
        backref="related_to",
    )

    # medias  -> backref from Media.evidence
    # custody -> backref from EvidenceCustody.evidence
    # history -> backref from EvidenceHistory.evidence

    # ------------------------------------------------------------------
    # Identifier
    # ------------------------------------------------------------------

    @staticmethod
    def generate_number() -> str:
        """Next EVD-000123 style identifier.

        Derived from the highest existing number rather than a row count, so
        archived or deleted rows cannot cause a collision.
        """
        last = (
            db.session.query(Evidence.evidence_number)
            .order_by(Evidence.id.desc())
            .limit(1)
            .scalar()
        )
        seq = 0
        if last and last.startswith("EVD-"):
            try:
                seq = int(last.split("-", 1)[1])
            except (ValueError, IndexError):
                seq = 0
        # A gap is preferable to a duplicate: walk forward until unused.
        while True:
            seq += 1
            candidate = f"EVD-{seq:06d}"
            exists = (
                db.session.query(Evidence.id).filter(Evidence.evidence_number == candidate).first()
            )
            if not exists:
                return candidate

    # ------------------------------------------------------------------
    # Access control
    # ------------------------------------------------------------------

    @property
    def restricted(self) -> bool:
        """Whether access roles are attached to this record."""
        return bool(self.roles)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_mini(self) -> dict[str, Any]:
        """Compact form for activity logs and relation widgets."""
        return {
            "id": self.id,
            "class": "evidence",
            "evidence_number": self.evidence_number,
            "case_code": self.case_code,
            "evidence_type": self.evidence_type,
            "status": self.status,
            "confidentiality": self.confidentiality,
        }

    def to_dict(self, include_media: bool = True) -> dict[str, Any]:
        data = {
            "id": self.id,
            "class": "evidence",
            "evidence_number": self.evidence_number,
            "case_code": self.case_code,
            "evidence_type": self.evidence_type,
            "description": self.description,
            "content_summary": self.content_summary,
            "source_information": self.source_information,
            "ownership_information": self.ownership_information,
            "evidence_date": DateHelper.serialize_datetime(self.evidence_date),
            "date_collected": DateHelper.serialize_datetime(self.date_collected),
            "collection_information": self.collection_information,
            "collector": self.collector,
            "collected_by": self.collected_by.to_compact() if self.collected_by else None,
            "collection_location": (
                self.collection_location.to_compact() if self.collection_location else None
            ),
            "consent_status": self.consent_status,
            "consent_information": self.consent_information,
            "relevance": self.relevance,
            "verification_information": self.verification_information,
            "confidentiality": self.confidentiality,
            "status": self.status,
            "notes": self.notes,
            "restricted": self.restricted,
            "user": self.user.to_compact() if self.user else None,
            "assigned_to": self.assigned_to.to_compact() if self.assigned_to else None,
            "roles": [{"id": r.id, "name": r.name, "color": r.color} for r in self.roles],
            "bulletins": [b.to_compact() for b in self.bulletins],
            "actors": [a.to_compact() for a in self.actors],
            "locations": [loc.to_compact() for loc in self.locations],
            "events": [e.to_dict() for e in self.events],
            "sources": [s.to_dict() for s in self.sources],
            "related_evidence": [e.to_mini() for e in self.related_evidence],
            "created_at": DateHelper.serialize_datetime(self.created_at),
            "updated_at": DateHelper.serialize_datetime(self.updated_at),
        }

        if include_media:
            medias = [m for m in (self.medias or []) if not m.deleted]
            data["medias"] = [m.to_dict() for m in medias]
            data["media_count"] = len(medias)

        # Custody is a sequence, so it is always returned oldest-first.
        data["custody"] = [
            c.to_dict()
            for c in sorted(self.custody or [], key=lambda c: (c.occurred_at or c.created_at))
        ]
        return data

    # ------------------------------------------------------------------
    # Deserialization
    # ------------------------------------------------------------------

    def from_json(self, json: dict[str, Any]) -> "Evidence":
        """Populate from request json.

        The identifier is never taken from input -- it is assigned once on
        creation and is not user-editable, so an evidence number cannot be
        reassigned to a different item.
        """
        from enferno.admin.models import Actor, Bulletin, Event, Location, Source
        from enferno.user.models import Role

        def scalar(key, current):
            return json.get(key, current)

        self.case_code = scalar("case_code", self.case_code)
        self.evidence_type = scalar("evidence_type", self.evidence_type)
        self.description = scalar("description", self.description)
        self.content_summary = scalar("content_summary", self.content_summary)
        self.source_information = scalar("source_information", self.source_information)
        self.ownership_information = scalar("ownership_information", self.ownership_information)
        self.collection_information = scalar("collection_information", self.collection_information)
        self.collector = scalar("collector", self.collector)
        self.consent_status = scalar("consent_status", self.consent_status)
        self.consent_information = scalar("consent_information", self.consent_information)
        self.relevance = scalar("relevance", self.relevance)
        self.verification_information = scalar(
            "verification_information", self.verification_information
        )
        self.confidentiality = scalar("confidentiality", self.confidentiality)
        self.status = scalar("status", self.status) or self.STATUS_DRAFT
        self.notes = scalar("notes", self.notes)

        if "evidence_date" in json:
            self.evidence_date = DateHelper.parse_datetime(json["evidence_date"])
        if "date_collected" in json:
            self.date_collected = DateHelper.parse_datetime(json["date_collected"])

        if "collection_location" in json:
            loc = json.get("collection_location")
            self.collection_location_id = loc.get("id") if loc else None

        if "assigned_to" in json:
            assignee = json.get("assigned_to")
            self.assigned_to_id = assignee.get("id") if assignee else None

        def relate(key, model, attr):
            if key not in json:
                return
            ids = [item.get("id") for item in (json.get(key) or []) if item.get("id")]
            setattr(self, attr, model.query.filter(model.id.in_(ids)).all() if ids else [])

        relate("bulletins", Bulletin, "bulletins")
        relate("actors", Actor, "actors")
        relate("locations", Location, "locations")
        relate("events", Event, "events")
        relate("sources", Source, "sources")
        relate("roles", Role, "roles")

        if "related_evidence" in json:
            ids = [
                item.get("id")
                for item in (json.get("related_evidence") or [])
                if item.get("id") and item.get("id") != self.id
            ]
            self.related_evidence = Evidence.query.filter(Evidence.id.in_(ids)).all() if ids else []

        return self

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def create_revision(self, user_id: Optional[int] = None, created: Any = None) -> None:
        """Snapshot the current state into the history table.

        Called after every save so an evidence record's field-level history is
        reconstructable, in the same way Bulletin revisions work.
        """
        from enferno.admin.models.EvidenceHistory import EvidenceHistory

        if not self.id:
            return
        revision = EvidenceHistory(
            evidence_id=self.id,
            data=self.to_dict(include_media=False),
            user_id=user_id,
        )
        if created:
            revision.created_at = created
        db.session.add(revision)
        db.session.commit()

    def __repr__(self) -> str:
        return f"<Evidence {self.evidence_number} status={self.status}>"
