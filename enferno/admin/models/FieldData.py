import json
from datetime import datetime
from typing import Any, Optional

import arrow
from sqlalchemy import ARRAY

from enferno.extensions import db
from enferno.admin.models.tables import field_data_locations
from enferno.utils.base import BaseMixin
from enferno.utils.date_helper import DateHelper
from enferno.utils.logging_utils import get_logger

logger = get_logger()


def parse_day(value: Any) -> Optional[datetime]:
    """Parse a calendar date into a naive datetime at midnight.

    DateHelper.parse_datetime only accepts "YYYY-MM-DDTHH:mm", but these are
    date-only columns and the UI submits "YYYY-MM-DD", which would otherwise
    fall through and silently store NULL.
    """
    if not value:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    for fmt in ("YYYY-MM-DD", "YYYY-MM-DDTHH:mm", "YYYY-MM-DDTHH:mm:ss"):
        try:
            return arrow.get(value, fmt).datetime.replace(tzinfo=None)
        except Exception:
            continue
    logger.error(f"Unparseable date value for FieldData: {value!r}")
    return None


def serialize_day(value: Any) -> Optional[str]:
    """Serialize a date column as "YYYY-MM-DD" for <input type="date">."""
    return arrow.get(value).format("YYYY-MM-DD") if value else None


# Free-text columns copied straight from the operator's field-data sheet.
STRING_FIELDS = (
    "name_of_site",
    "collected_data_by",
    "type_of_site",
    "code",
    "translation",
    "data_size_for_site",
    "total_size",
    "data_storage_location",
    "analysis_by",
    "shared_with",
    "excavated_status",
)

# Counts. Blank cells stay NULL rather than becoming 0, so "not recorded"
# remains distinguishable from "recorded as none".
INTEGER_FIELDS = (
    "no_of_site",
    "total_photos",
    "total_videos",
    "total_interviews",
    "drone_photos",
    "drone_videos",
)

DATE_FIELDS = ("mission_date", "analysis_date")


class FieldData(db.Model, BaseMixin):
    """
    SQL Alchemy model for field data collected during site missions.
    """

    __tablename__ = "field_data"
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)

    # Site identification
    name_of_site = db.Column(db.String, index=True, nullable=False)
    mission_date = db.Column(db.DateTime, index=True)
    collected_data_by = db.Column(db.String)
    data_types = db.Column(ARRAY(db.String), default=[])
    type_of_site = db.Column(db.String, index=True)
    no_of_site = db.Column(db.Integer)
    code = db.Column(db.String, index=True)

    # Collected media counts
    total_photos = db.Column(db.Integer)
    total_videos = db.Column(db.Integer)
    total_interviews = db.Column(db.Integer)
    translation = db.Column(db.String)
    drone_photos = db.Column(db.Integer)
    drone_videos = db.Column(db.Integer)

    # Storage. Sizes are free text so units ("1.2 TB") survive round-tripping.
    data_size_for_site = db.Column(db.String)
    total_size = db.Column(db.String)
    data_storage_location = db.Column(db.String)

    # Analysis
    legal_analysis = db.Column(db.Text)
    analysis_by = db.Column(db.String)
    analysis_date = db.Column(db.DateTime)
    shared_with = db.Column(db.String)

    # Maintained by the API, not accepted from the client. created_by is set
    # once at creation; the modified_* pair is refreshed on every write.
    created_by = db.Column(db.String)
    modified_last_by = db.Column(db.String)
    modified_last_date = db.Column(db.DateTime)

    excavated_status = db.Column(db.String, index=True)

    # Rich-text narrative, same TinyMCE editor Bulletin uses.
    description = db.Column(db.Text)

    # Where this location's bulk data lives outside Bayanat (NAS path, share,
    # or URL). Stored verbatim; opening it is the browser's business.
    external_link = db.Column(db.String)

    sites = db.relationship(
        "FieldDataSite",
        backref="location",
        order_by="FieldDataSite.sort_order",
        cascade="all, delete-orphan",
    )

    # The shared Location entity, same as Bulletin uses.
    locations = db.relationship(
        "Location",
        secondary=field_data_locations,
        backref=db.backref("field_data_records", lazy="dynamic"),
    )

    # How many separate times this site has been documented.
    times_documented = db.Column(db.Integer)

    # Interviews conducted at the site. Names are only meaningful when the
    # flag is set; clearing the flag clears the names (see from_json).
    has_interview = db.Column(db.Boolean, default=False, nullable=False, server_default="false")
    interview_names = db.Column(ARRAY(db.String), default=[])

    def from_json(self, json: dict[str, Any]) -> "FieldData":
        """Populate the record from a validated request payload."""
        for field in STRING_FIELDS:
            if field in json:
                value = json.get(field)
                setattr(self, field, value.strip() if isinstance(value, str) else value)

        for field in INTEGER_FIELDS:
            if field in json:
                value = json.get(field)
                # "" arrives from cleared number inputs; treat it as unset.
                setattr(self, field, None if value in ("", None) else int(value))

        for field in DATE_FIELDS:
            if field in json:
                setattr(self, field, parse_day(json.get(field)))

        if "data_types" in json:
            self.data_types = json.get("data_types") or []

        if "legal_analysis" in json:
            self.legal_analysis = json.get("legal_analysis")

        if "description" in json:
            self.description = json.get("description")

        if "external_link" in json:
            value = json.get("external_link")
            self.external_link = value.strip() if isinstance(value, str) else value

        if "locations" in json:
            from enferno.admin.models.Location import Location

            ids = [loc["id"] for loc in (json.get("locations") or []) if loc.get("id")]
            self.locations = Location.query.filter(Location.id.in_(ids)).all() if ids else []

        if "times_documented" in json:
            value = json.get("times_documented")
            self.times_documented = None if value in ("", None) else int(value)

        if "has_interview" in json:
            self.has_interview = bool(json.get("has_interview"))

        if "interview_names" in json:
            names = [n.strip() for n in (json.get("interview_names") or []) if n and n.strip()]
            self.interview_names = names

        # Names without the flag would be invisible in the UI but still
        # searchable, so keep the two consistent.
        if not self.has_interview:
            self.interview_names = []

        self.sync_sites(json)
        self.sync_medias(json)

        return self

    def sync_sites(self, json: dict[str, Any]) -> None:
        """Replace the site list from the payload, preserving existing rows.

        Sites carry their own data, so an edit must update matching rows rather
        than recreate them (which would lose their ids and orphan nothing but
        churn the table). delete-orphan on the relationship removes any site
        the operator dropped from the form.
        """
        if "sites" not in json:
            return

        from enferno.admin.models.FieldDataSite import FieldDataSite

        submitted = json.get("sites") or []
        existing = {site.id: site for site in self.sites}
        ordered = []

        for position, payload in enumerate(submitted):
            site = existing.get(payload.get("id")) if payload.get("id") else None
            if site is None:
                site = FieldDataSite()
            site.from_json(payload)
            # Position in the form is the source of truth: first row is primary.
            site.sort_order = position
            ordered.append(site)

        # delete-orphan will destroy sites dropped from the form, so their
        # media has to let go of them first or the DELETE violates
        # fk_media_field_data_site_id.
        kept = {id(site) for site in ordered}
        for site in self.sites:
            if id(site) not in kept:
                site.release_medias()
        db.session.flush()

        self.sites = ordered

    def sync_medias(self, json: dict[str, Any]) -> None:
        """Attach newly uploaded media and soft-delete removed ones.

        Mirrors Bulletin.from_json: media rows are never hard-deleted, so a
        file stays recoverable after being detached from the record.
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

    def delete(self, raise_exception: bool = False):
        """Soft-delete the record and hide its media.

        Deliberately not a row DELETE. A hard delete here is unrecoverable --
        there is no revision history for this entity -- and an accidental click
        has already cost real records once. Every read path filters
        deleted == False, so the row disappears from the UI either way.

        field_data_id is left intact so restoring is just flipping the flags:
            UPDATE field_data SET deleted = false WHERE id = :id;
            UPDATE media SET deleted = false WHERE field_data_id = :id;
        """
        from sqlalchemy import update

        from enferno.admin.models.Media import Media

        try:
            # Core UPDATE: enferno/utils/soft_delete.py installs a global
            # do_orm_execute listener that hides deleted media from ORM
            # queries, so self.medias cannot be relied on to see every row.
            db.session.execute(
                update(Media.__table__)
                .where(Media.__table__.c.field_data_id == self.id)
                .values(deleted=True)
            )
            # Media hanging off this location's sites is hidden too, but the
            # FK is left alone so restoring the location brings it all back.
            site_ids = [site.id for site in self.sites if site.id]
            if site_ids:
                db.session.execute(
                    update(Media.__table__)
                    .where(Media.__table__.c.field_data_site_id.in_(site_ids))
                    .values(deleted=True)
                )
            self.deleted = True
            db.session.add(self)
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting FieldData: {e}")
            if raise_exception:
                raise
            return False

    def stamp_modified_by(self, user: Any) -> "FieldData":
        """Record who last touched this row and when.

        The sheet tracked this by hand; deriving it from the session keeps it
        accurate and prevents backdating. Also fills created_by the first time,
        so existing rows adopt an author on their next save.
        """
        username = getattr(user, "username", None)
        if not self.created_by:
            self.created_by = username
        self.modified_last_by = username
        self.modified_last_date = DateHelper.utcnow()
        return self

    def to_dict(self) -> dict[str, Any]:
        """Return a dictionary representation of the field data record."""
        data = {"id": self.id, "class": self.__tablename__}

        for field in STRING_FIELDS + INTEGER_FIELDS:
            data[field] = getattr(self, field)

        for field in DATE_FIELDS:
            data[field] = serialize_day(getattr(self, field))

        data["created_by"] = self.created_by
        data["data_types"] = self.data_types or []
        data["legal_analysis"] = self.legal_analysis
        data["description"] = self.description
        data["external_link"] = self.external_link
        data["sites"] = [site.to_dict() for site in self.sites]
        data["locations"] = [loc.to_compact() for loc in self.locations]
        data["times_documented"] = self.times_documented
        data["has_interview"] = bool(self.has_interview)
        data["interview_names"] = self.interview_names or []
        data["medias"] = [m.to_dict() for m in self.medias if not m.deleted]
        data["modified_last_by"] = self.modified_last_by
        data["modified_last_date"] = (
            DateHelper.serialize_datetime(self.modified_last_date)
            if self.modified_last_date
            else None
        )
        data["updated_at"] = (
            DateHelper.serialize_datetime(self.updated_at) if self.updated_at else None
        )
        return data

    def to_mini(self) -> dict[str, Any]:
        """Compact representation used for activity logging."""
        return {
            "id": self.id,
            "class": self.__tablename__,
            "name_of_site": self.name_of_site,
            "code": self.code,
        }

    def __repr__(self) -> str:
        return "<FieldData {} {}>".format(self.id, self.name_of_site)

    def to_json(self) -> str:
        """Return a JSON representation of the field data record."""
        return json.dumps(self.to_dict())

    @staticmethod
    def find_by_code(code: str) -> Optional["FieldData"]:
        """Find a record by its site code."""
        return FieldData.query.filter(FieldData.code.ilike(code)).first()
