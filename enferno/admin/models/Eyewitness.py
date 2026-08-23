"""Eyewitness capture records.

What a capture app hands over when someone documents an incident: which item on
which device, recorded by whom, when and where, with what the person said about
it at the time.

The section exists so that capture metadata is held once and referenced, rather
than retyped onto every exhibit that came out of the same recording. Anything
Bayanat already models -- the event, the alleged perpetrator, the place, the
tags -- is linked rather than restated, so a correction to a perpetrator or a
location is made in one place and every capture referencing it follows.

District and governorate are deliberately *not* columns. They are read from the
captured location's own admin hierarchy (Bayanat already holds Governorate and
District as admin levels 1 and 2), so they can never contradict the location
they are supposed to describe.
"""

from __future__ import annotations

from typing import Any, Optional

from enferno.admin.models.tables import (
    eyewitness_actors,
    eyewitness_bulletins,
    eyewitness_evidence,
    eyewitness_field_data,
    eyewitness_labels,
    eyewitness_roles,
)
from enferno.extensions import db
from enferno.utils.base import BaseMixin
from enferno.utils.date_helper import DateHelper
from enferno.utils.logging_utils import get_logger

logger = get_logger()


class Eyewitness(db.Model, BaseMixin):
    """A single capture handed over by an eyewitness."""

    __tablename__ = "eyewitness"
    __table_args__ = {"extend_existing": True}

    STATUS_DRAFT = "Draft"
    STATUS_REVIEW = "Under Review"
    STATUS_VERIFIED = "Verified"
    STATUS_ARCHIVED = "Archived"
    STATUSES = [STATUS_DRAFT, STATUS_REVIEW, STATUS_VERIFIED, STATUS_ARCHIVED]

    id = db.Column(db.Integer, primary_key=True)

    # The capture app's own identifier for the item. Not generated here: it is
    # what the person reading the phone will quote, so it is stored as given.
    # Indexed rather than unique -- two devices may legitimately reuse a number.
    item_id = db.Column(db.String, index=True)

    # How many files/items the capture covers, when one record stands for a set.
    number_of_items = db.Column(db.Integer)

    device_id = db.Column(db.String, index=True)
    # The account name used in the capture app, which is not a Bayanat user.
    username = db.Column(db.String, index=True)

    # --- what was captured -----------------------------------------------
    alleged_event_id = db.Column(db.Integer, db.ForeignKey("event.id"), index=True)
    alleged_event = db.relationship("Event", foreign_keys=[alleged_event_id])

    event_description = db.Column(db.Text)
    # What the capturing person wrote at the time, kept apart from the
    # description so a later editor never overwrites the original account.
    user_notes = db.Column(db.Text)

    # --- when and where ---------------------------------------------------
    date_of_capture = db.Column(db.DateTime, index=True)

    capture_location_id = db.Column(db.Integer, db.ForeignKey("location.id"), index=True)
    capture_location = db.relationship("Location", foreign_keys=[capture_location_id])

    # The GPS reading taken at the moment of capture. Kept alongside the linked
    # location rather than instead of it: the location says where this belongs
    # in the archive's own geography, the coordinates say where the device
    # actually was, and the two are not always the same claim.
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)

    status = db.Column(db.String, index=True, default=STATUS_DRAFT)

    # --- ownership within Bayanat ----------------------------------------
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    user = db.relationship("User", foreign_keys=[user_id])
    assigned_to_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    assigned_to = db.relationship("User", foreign_keys=[assigned_to_id])

    # `deleted`, `created_at` and `updated_at` come from BaseMixin.

    # --- relationships ----------------------------------------------------
    roles = db.relationship(
        "Role", secondary=eyewitness_roles, backref=db.backref("eyewitness", lazy="dynamic")
    )
    bulletins = db.relationship(
        "Bulletin", secondary=eyewitness_bulletins, backref=db.backref("eyewitness", lazy="dynamic")
    )
    # "Alleged perpetrator" -- plural because a capture may implicate more than
    # one, and alleged because nothing here is a finding.
    alleged_perpetrators = db.relationship(
        "Actor", secondary=eyewitness_actors, backref=db.backref("eyewitness", lazy="dynamic")
    )
    # "Tags used" in the capture app, mapped onto Bayanat's own labels.
    tags = db.relationship(
        "Label", secondary=eyewitness_labels, backref=db.backref("eyewitness", lazy="dynamic")
    )
    evidence_items = db.relationship(
        "Evidence", secondary=eyewitness_evidence, backref=db.backref("eyewitness", lazy="dynamic")
    )
    field_data = db.relationship(
        "FieldData",
        secondary=eyewitness_field_data,
        backref=db.backref("eyewitness", lazy="dynamic"),
    )

    # medias -> backref from Media.eyewitness

    # ------------------------------------------------------------------
    # Derived location detail
    # ------------------------------------------------------------------

    def _location_at_level(self, level_code: int) -> Optional[str]:
        """Walk up the captured location to the requested admin level.

        Governorate is level 1 and District level 2 in Bayanat's admin levels,
        so this reads the answer off the hierarchy rather than storing a copy
        that could drift out of step with it.
        """
        node = self.capture_location
        seen = set()
        while node is not None and node.id not in seen:
            seen.add(node.id)
            level = getattr(node, "admin_level", None)
            code = getattr(level, "code", None) if level else None
            if code is not None and int(code) == level_code:
                return node.title
            node = getattr(node, "parent", None)
        return None

    @property
    def governorate(self) -> Optional[str]:
        return self._location_at_level(1)

    @property
    def district(self) -> Optional[str]:
        return self._location_at_level(2)

    @property
    def site_name(self) -> Optional[str]:
        """The name of the field-data site visit this capture belongs to."""
        for item in self.field_data or []:
            if item.name_of_site:
                return item.name_of_site
        return None

    @property
    def location_name(self) -> Optional[str]:
        """What to show as the capture's location.

        A capture is recorded against a site visit, so the site's own name is
        the location in practice. An explicitly chosen Location still wins --
        it is a deliberate, more precise statement than the mission's label --
        and the site name fills in when none was picked.
        """
        if self.capture_location is not None and self.capture_location.title:
            return self.capture_location.title
        return self.site_name

    @property
    def district_governorate(self) -> Optional[str]:
        """"District - Governorate", or whichever half is known."""
        parts = [p for p in (self.district, self.governorate) if p]
        return " - ".join(parts) if parts else None

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_mini(self) -> dict[str, Any]:
        """Compact form for activity logs and relation widgets."""
        return {
            "id": self.id,
            "class": "eyewitness",
            "item_id": self.item_id,
            "device_id": self.device_id,
            "username": self.username,
            "status": self.status,
        }

    def to_dict(self, include_media: bool = True) -> dict[str, Any]:
        def ref(obj):
            if obj is None:
                return None
            return {
                "id": obj.id,
                "title": getattr(obj, "title", None) or getattr(obj, "name", None),
            }

        data = {
            "id": self.id,
            "class": "eyewitness",
            "item_id": self.item_id,
            "number_of_items": self.number_of_items,
            "device_id": self.device_id,
            "username": self.username,
            "alleged_event": ref(self.alleged_event),
            "event_description": self.event_description,
            "user_notes": self.user_notes,
            "date_of_capture": DateHelper.serialize_datetime(self.date_of_capture),
            "capture_location": (
                {
                    "id": self.capture_location.id,
                    "title": self.capture_location.title,
                    "full_string": getattr(self.capture_location, "full_location", None)
                    or self.capture_location.title,
                }
                if self.capture_location
                else None
            ),
            # What the list shows under "Location": the chosen Location if there
            # is one, otherwise the name of the site visit that produced this.
            "location_name": self.location_name,
            "site_name": self.site_name,
            "district": self.district,
            "governorate": self.governorate,
            "district_governorate": self.district_governorate,
            # Shaped as GeoMap expects so the picker can bind to it directly.
            "geo": (
                {"lat": self.latitude, "lng": self.longitude}
                if self.latitude is not None and self.longitude is not None
                else None
            ),
            "latitude": self.latitude,
            "longitude": self.longitude,
            "status": self.status,
            "tags": [ref(t) for t in (self.tags or [])],
            "alleged_perpetrators": [ref(a) for a in (self.alleged_perpetrators or [])],
            "bulletins": [ref(b) for b in (self.bulletins or [])],
            "evidence_items": [
                {"id": e.id, "title": e.evidence_number, "case_code": e.case_code}
                for e in (self.evidence_items or [])
            ],
            "field_data": [
                {"id": f.id, "title": f.name_of_site, "code": f.code}
                for f in (self.field_data or [])
            ],
            "roles": [{"id": r.id, "name": r.name} for r in (self.roles or [])],
            "assigned_to": (
                {"id": self.assigned_to.id, "name": self.assigned_to.name}
                if self.assigned_to
                else None
            ),
            "created_at": DateHelper.serialize_datetime(self.created_at),
            "updated_at": DateHelper.serialize_datetime(self.updated_at),
        }

        if include_media:
            medias = [m for m in (self.medias or []) if not m.deleted]
            data["medias"] = [m.to_dict() for m in medias]
            data["media_count"] = len(medias)

            # Media reached through the linked evidence, listed separately so the
            # capture shows everything it produced without the files having to be
            # attached to both records.
            related = []
            for item in self.evidence_items or []:
                for m in item.medias or []:
                    if not m.deleted:
                        entry = m.to_dict()
                        entry["via_evidence"] = item.evidence_number
                        related.append(entry)
            data["evidence_medias"] = related

        return data

    # ------------------------------------------------------------------
    # Deserialisation
    # ------------------------------------------------------------------

    def from_json(self, json: dict[str, Any]) -> "Eyewitness":
        from enferno.admin.models import (
            Actor,
            Bulletin,
            Evidence,
            Event,
            FieldData,
            Label,
            Location,
        )
        from enferno.user.models import Role

        def scalar(key, current):
            return json.get(key, current)

        self.item_id = scalar("item_id", self.item_id)
        self.device_id = scalar("device_id", self.device_id)
        self.username = scalar("username", self.username)
        self.event_description = scalar("event_description", self.event_description)
        self.user_notes = scalar("user_notes", self.user_notes)
        self.status = scalar("status", self.status)

        if "number_of_items" in json:
            raw = json.get("number_of_items")
            try:
                self.number_of_items = int(raw) if raw not in (None, "") else None
            except (TypeError, ValueError):
                # A non-numeric count is dropped rather than raised: the rest of
                # the capture is still worth saving.
                logger.warning(f"Ignoring non-numeric number_of_items: {raw!r}")

        if "date_of_capture" in json:
            self.date_of_capture = DateHelper.parse_datetime(json.get("date_of_capture"))

        def single(key, model, attr_id):
            if key not in json:
                return
            value = json.get(key)
            setattr(self, attr_id, value.get("id") if isinstance(value, dict) else value or None)

        single("alleged_event", Event, "alleged_event_id")
        single("capture_location", Location, "capture_location_id")

        def many(key, model):
            ids = [i.get("id") if isinstance(i, dict) else i for i in (json.get(key) or [])]
            ids = [i for i in ids if i]
            return model.query.filter(model.id.in_(ids)).all() if ids else []

        if "alleged_perpetrators" in json:
            self.alleged_perpetrators = many("alleged_perpetrators", Actor)
        if "tags" in json:
            self.tags = many("tags", Label)
        if "bulletins" in json:
            self.bulletins = many("bulletins", Bulletin)
        if "evidence_items" in json:
            self.evidence_items = many("evidence_items", Evidence)
        if "field_data" in json:
            self.field_data = many("field_data", FieldData)

        # The map hands back {lat, lng}; clearing the marker clears both, so a
        # half-set coordinate can never be stored.
        if "geo" in json:
            geo = json.get("geo") or {}
            lat, lng = geo.get("lat"), geo.get("lng")
            try:
                self.latitude = float(lat) if lat not in (None, "") else None
                self.longitude = float(lng) if lng not in (None, "") else None
            except (TypeError, ValueError):
                logger.warning(f"Ignoring unusable capture coordinates: {geo!r}")
        if "roles" in json:
            self.roles = many("roles", Role)
        if "assigned_to" in json:
            value = json.get("assigned_to")
            self.assigned_to_id = value.get("id") if isinstance(value, dict) else value or None

        return self

    def __repr__(self) -> str:
        return f"<Eyewitness {self.id} item={self.item_id} status={self.status}>"
