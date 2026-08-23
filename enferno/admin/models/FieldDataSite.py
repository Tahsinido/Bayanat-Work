"""A single site recorded under a Field Data location.

A location (FieldData) can hold several sites -- the first is the primary one,
the rest follow in sort_order -- and each site carries its own collection
figures, storage details and analysis, so they can be filled in separately.
"""

from typing import Any, Optional

from sqlalchemy import ARRAY

from enferno.extensions import db
from enferno.utils.base import BaseMixin
from enferno.utils.logging_utils import get_logger

logger = get_logger()

STRING_FIELDS = (
    "site_name",
    "collected_data_by",
    "type_of_site",
    "code",
    "translation",
    "data_size_for_site",
    "total_size",
    "data_storage_location",
    "external_link",
    "analysis_by",
    "shared_with",
    "excavated_status",
)

INTEGER_FIELDS = (
    "no_of_site",
    "total_photos",
    "total_videos",
    "total_interviews",
    "drone_photos",
    "drone_videos",
    "times_documented",
)

DATE_FIELDS = ("mission_date", "analysis_date")

TEXT_FIELDS = ("description", "legal_analysis")


class FieldDataSite(db.Model, BaseMixin):
    """SQL Alchemy model for a site belonging to a field data location."""

    __tablename__ = "field_data_site"
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    field_data_id = db.Column(
        db.Integer, db.ForeignKey("field_data.id"), index=True, nullable=False
    )

    # 0 is the primary site; the UI keeps this contiguous on save.
    sort_order = db.Column(db.Integer, default=0, nullable=False, server_default="0")

    site_name = db.Column(db.String, index=True, nullable=False)

    # Where this particular site sits. Separate graves or buildings under one
    # field location stand metres apart, so a site may carry its own reading;
    # left blank it falls back to the parent location's markers in the UI.
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)

    mission_date = db.Column(db.DateTime)
    collected_data_by = db.Column(db.String)
    data_types = db.Column(ARRAY(db.String), default=[])
    type_of_site = db.Column(db.String, index=True)
    no_of_site = db.Column(db.Integer)
    code = db.Column(db.String, index=True)

    total_photos = db.Column(db.Integer)
    total_videos = db.Column(db.Integer)
    total_interviews = db.Column(db.Integer)
    translation = db.Column(db.String)
    drone_photos = db.Column(db.Integer)
    drone_videos = db.Column(db.Integer)

    data_size_for_site = db.Column(db.String)
    total_size = db.Column(db.String)
    data_storage_location = db.Column(db.String)
    # Path/URL to this site's data held outside Bayanat.
    external_link = db.Column(db.String)

    description = db.Column(db.Text)
    legal_analysis = db.Column(db.Text)
    analysis_by = db.Column(db.String)
    analysis_date = db.Column(db.DateTime)
    shared_with = db.Column(db.String)
    excavated_status = db.Column(db.String, index=True)

    times_documented = db.Column(db.Integer)
    has_interview = db.Column(db.Boolean, default=False, nullable=False, server_default="false")
    interview_names = db.Column(ARRAY(db.String), default=[])

    def from_json(self, json: dict[str, Any]) -> "FieldDataSite":
        """Populate the site from a validated payload fragment."""
        from enferno.admin.models.FieldData import parse_day

        for field in STRING_FIELDS:
            if field in json:
                value = json.get(field)
                setattr(self, field, value.strip() if isinstance(value, str) else value)

        for field in INTEGER_FIELDS:
            if field in json:
                value = json.get(field)
                setattr(self, field, None if value in ("", None) else int(value))

        for field in DATE_FIELDS:
            if field in json:
                setattr(self, field, parse_day(json.get(field)))

        for field in TEXT_FIELDS:
            if field in json:
                setattr(self, field, json.get(field))

        if "data_types" in json:
            self.data_types = json.get("data_types") or []

        # Shaped the way GeoMap binds, so the picker writes straight back.
        # Unusable coordinates are dropped rather than failing the whole save --
        # the rest of the site is still worth keeping.
        if "geo" in json:
            geo = json.get("geo") or {}
            lat, lng = geo.get("lat"), geo.get("lng")
            try:
                self.latitude = float(lat) if lat not in (None, "") else None
                self.longitude = float(lng) if lng not in (None, "") else None
            except (TypeError, ValueError):
                logger.warning(f"Ignoring unusable site coordinates: {geo!r}")

        if "sort_order" in json and json.get("sort_order") is not None:
            self.sort_order = int(json["sort_order"])

        if "has_interview" in json:
            self.has_interview = bool(json.get("has_interview"))

        if "interview_names" in json:
            names = [n.strip() for n in (json.get("interview_names") or []) if n and n.strip()]
            self.interview_names = names

        if not self.has_interview:
            self.interview_names = []

        self.sync_medias(json)

        return self

    def sync_medias(self, json: dict[str, Any]) -> None:
        """Attach newly uploaded media to this site, detaching removed ones.

        Media rows are soft-deleted rather than destroyed, so a file stays
        recoverable after being taken off the site.
        """
        if "medias" not in json:
            return

        from enferno.admin.models.Media import Media

        submitted = json.get("medias") or []
        keep_ids = {m.get("id") for m in submitted if m.get("id")}

        existing = [m for m in self.medias if m.id in keep_ids]
        removed = [m for m in self.medias if m.id not in keep_ids]

        created = []
        for media in [m for m in submitted if not m.get("id")]:
            m = Media()
            m = m.from_json(media)
            m.save()
            created.append(m)

        self.medias = existing + created

        for media in removed:
            media.deleted = True
            media.save()

    def release_medias(self) -> None:
        """Soft-delete and detach every media row pointing at this site.

        Called before the site row is removed. Without clearing the FK the
        delete fails against fk_media_field_data_site_id, and the global
        soft-delete loader filter hides already-deleted rows from self.medias,
        so this goes through Core rather than the relationship.
        """
        from sqlalchemy import update

        from enferno.admin.models.Media import Media

        if not self.id:
            return

        db.session.execute(
            update(Media.__table__)
            .where(Media.__table__.c.field_data_site_id == self.id)
            .values(deleted=True, field_data_site_id=None)
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a dictionary representation of the site."""
        from enferno.admin.models.FieldData import serialize_day

        data = {"id": self.id, "sort_order": self.sort_order}
        for field in STRING_FIELDS + INTEGER_FIELDS + TEXT_FIELDS:
            data[field] = getattr(self, field)
        for field in DATE_FIELDS:
            data[field] = serialize_day(getattr(self, field))
        data["data_types"] = self.data_types or []
        data["latitude"] = self.latitude
        data["longitude"] = self.longitude
        data["geo"] = (
            {"lat": self.latitude, "lng": self.longitude}
            if self.latitude is not None and self.longitude is not None
            else None
        )
        data["has_interview"] = bool(self.has_interview)
        data["interview_names"] = self.interview_names or []
        data["medias"] = [m.to_dict() for m in self.medias if not m.deleted]
        return data

    def __repr__(self) -> str:
        return "<FieldDataSite {} {}>".format(self.id, self.site_name)
