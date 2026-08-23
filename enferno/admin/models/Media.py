import json
import pathlib
import secrets
from pathlib import Path
from typing import Any
from unidecode import unidecode

from werkzeug.utils import secure_filename

from enferno.extensions import db
from enferno.utils.base import BaseMixin
from enferno.utils.date_helper import DateHelper
from enferno.utils.logging_utils import get_logger
from enferno.admin.models.MediaCategory import MediaCategory
from enferno.admin.models.utils import check_roles

logger = get_logger()


class Media(db.Model, BaseMixin):
    """
    SQL Alchemy model for media
    """

    # __table_args__ = {"extend_existing": True}

    extend_existing = True

    __table_args__ = (
        db.Index(
            "ix_media_etag_bulletin_unique",
            "etag",
            "bulletin_id",
            unique=True,
            postgresql_where=db.text("deleted = FALSE AND bulletin_id IS NOT NULL"),
        ),
        db.Index(
            "ix_media_etag_actor_unique",
            "etag",
            "actor_id",
            unique=True,
            postgresql_where=db.text("deleted = FALSE AND actor_id IS NOT NULL"),
        ),
    )

    # set media directory here (could be set in the settings)
    media_dir = Path("enferno/media")
    inline_dir = Path("enferno/media/inline")
    id = db.Column(db.Integer, primary_key=True)
    media_file = db.Column(db.String, nullable=False)
    media_file_type = db.Column(db.String, nullable=False)
    category = db.Column(db.Integer)
    etag = db.Column(db.String, index=True)
    duration = db.Column(db.String)
    orientation = db.Column(db.Integer, default=0)

    title = db.Column(db.String)
    title_ar = db.Column(db.String)
    comments = db.Column(db.String)
    comments_ar = db.Column(db.String)
    search = db.Column(
        db.Text,
        db.Computed("""
            CAST(id AS TEXT) || ' ' ||
            COALESCE(title, '') || ' ' ||
            COALESCE(media_file, '') || ' ' ||
            COALESCE(media_file_type, '') || ' ' ||
            COALESCE(comments, '')
            """),
    )

    time = db.Column(db.Float())

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    user = db.relationship("User", backref="user_medias", foreign_keys=[user_id])

    bulletin_id = db.Column(db.Integer, db.ForeignKey("bulletin.id"))
    bulletin = db.relationship("Bulletin", backref="medias", foreign_keys=[bulletin_id])

    actor_id = db.Column(db.Integer, db.ForeignKey("actor.id"))
    actor = db.relationship("Actor", backref="medias", foreign_keys=[actor_id])

    field_data_id = db.Column(db.Integer, db.ForeignKey("field_data.id"), index=True)
    field_data = db.relationship("FieldData", backref="medias", foreign_keys=[field_data_id])

    field_data_site_id = db.Column(
        db.Integer, db.ForeignKey("field_data_site.id"), index=True
    )
    field_data_site = db.relationship(
        "FieldDataSite", backref="medias", foreign_keys=[field_data_site_id]
    )

    # Media attached to an evidence record. Follows the same nullable-FK pattern
    # as the parents above, which is what lets a file hang off a Bulletin
    # directly as well as off Evidence -- Case/Bulletin -> Evidence -> Media,
    # with the shortcut Case/Bulletin -> Media still available.
    evidence_id = db.Column(
        db.Integer, db.ForeignKey("evidence.id", ondelete="CASCADE"), index=True
    )
    evidence = db.relationship("Evidence", backref="medias", foreign_keys=[evidence_id])

    # A file may hang off an eyewitness capture instead of an exhibit -- the raw
    # recording as it left the device, before anyone decided what part of it is
    # the exhibit. Separate column rather than reusing evidence_id so a file is
    # never implicitly promoted to evidence by being uploaded.
    eyewitness_id = db.Column(
        db.Integer, db.ForeignKey("eyewitness.id", ondelete="CASCADE"), index=True
    )
    eyewitness = db.relationship("Eyewitness", backref="medias", foreign_keys=[eyewitness_id])

    # ------------------------------------------------------------------
    # Evidentiary metadata
    #
    # Descriptive fields for media held as evidence. Nullable throughout: media
    # attached to a bulletin or actor in the ordinary way carries none of this,
    # and nothing here is required to display or serve a file.
    #
    # Human-readable identifier (IMG-000456 / VID-000457 / DOC-000458), so a
    # media item can be cited in correspondence and on custody forms without
    # depending on the original filename.
    # ------------------------------------------------------------------
    media_number = db.Column(db.String, unique=True, index=True)
    description = db.Column(db.Text)

    # When the material was created or recorded, as distinct from when it
    # reached us (date_obtained) or when it was uploaded (created_at).
    date_recorded = db.Column(db.DateTime)
    date_obtained = db.Column(db.DateTime)

    location_id = db.Column(db.Integer, db.ForeignKey("location.id"))
    location = db.relationship("Location", foreign_keys=[location_id])
    source_id = db.Column(db.Integer, db.ForeignKey("source.id"))
    source = db.relationship("Source", foreign_keys=[source_id])

    # Free text: the creator is often not a Bayanat user.
    creator = db.Column(db.String)
    # The person the media is about or from.
    person_actor_id = db.Column(db.Integer, db.ForeignKey("actor.id"))
    person_actor = db.relationship("Actor", foreign_keys=[person_actor_id])
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"))
    event = db.relationship("Event", foreign_keys=[event_id])

    relevance = db.Column(db.Text)
    confidentiality = db.Column(db.String, index=True)
    consent_status = db.Column(db.String)
    custody_reference = db.Column(db.String)

    # Monotonic per media item, bumped when a file is replaced rather than
    # overwritten silently.
    version = db.Column(db.Integer, default=1, server_default="1")
    status = db.Column(db.String, index=True)
    notes = db.Column(db.Text)

    main = db.Column(db.Boolean, default=False)

    # custom serialization method
    @check_roles
    def to_dict(self) -> dict[str, Any]:
        """Return a dictionary representation of the media."""
        media_category = db.session.get(MediaCategory, self.category) if self.category else None
        return {
            "id": self.id,
            "title": self.title if self.title else None,
            "title_ar": self.title_ar if self.title_ar else None,
            "category": media_category.to_dict() if media_category else None,
            "fileType": self.media_file_type if self.media_file_type else None,
            "filename": self.media_file if self.media_file else None,
            "etag": getattr(self, "etag", None),
            "time": getattr(self, "time", None),
            "duration": self.duration,
            "main": self.main,
            "orientation": self.orientation or 0,
            "updated_at": (
                DateHelper.serialize_datetime(self.updated_at) if self.updated_at else None
            ),
            "extraction": self.extraction.to_compact_dict() if self.extraction else None,
            "isRedaction": self.redaction is not None,
            "originalMediaId": self.redaction.original_media_id if self.redaction else None,
            # Evidentiary metadata. Always present in the payload so a client can
            # render the evidence view without a second request; null for media
            # attached in the ordinary way.
            "media_number": self.media_number,
            "evidence_id": self.evidence_id,
            "description": self.description,
            "date_recorded": DateHelper.serialize_datetime(self.date_recorded),
            "date_obtained": DateHelper.serialize_datetime(self.date_obtained),
            "location": self.location.to_compact() if self.location else None,
            "source": self.source.to_dict() if self.source else None,
            "creator": self.creator,
            "person_actor": self.person_actor.to_compact() if self.person_actor else None,
            "event": self.event.to_dict() if self.event else None,
            "relevance": self.relevance,
            "confidentiality": self.confidentiality,
            "consent_status": self.consent_status,
            "custody_reference": self.custody_reference,
            "version": self.version or 1,
            "status": self.status,
            "notes": self.notes,
            "uploaded_by": self.user.to_compact() if self.user else None,
            "upload_date": DateHelper.serialize_datetime(self.created_at),
        }

    def to_json(self) -> str:
        """Return a JSON representation of the media."""
        return json.dumps(self.to_dict())

    # populates model from json dict
    def from_json(self, json: dict[str, Any]) -> "Media":
        """
        Create a media object from a json dictionary.

        Args:
            - json: the json dictionary to create the media from.

        Returns:
            - the media object.
        """
        self.title = json["title"] if "title" in json else None
        self.title_ar = json["title_ar"] if "title_ar" in json else None
        self.media_file_type = json["fileType"] if "fileType" in json else None
        self.media_file = json["filename"] if "filename" in json else None
        self.etag = json.get("etag", None)
        self.time = json.get("time", None)
        category = json.get("category", None)
        if category:
            self.category = category.get("id")
        return self

    # generate custom file name for upload purposes
    @staticmethod
    def generate_file_name(filename: str) -> str:
        """
        Generate a secure and timestamped file name.

        Args:
            - filename: the original file name.

        Returns:
            - the generated file name.
        """
        decoded = secure_filename(unidecode(filename)).lower()
        return f"{DateHelper.utcnow().strftime('%Y%m%d-%H%M%S')}-{decoded}"

    @staticmethod
    def generate_inline_file_name(filename: str) -> str:
        """Opaque, unguessable name for inline rich-text uploads (BAY-01-020).

        Inline media is served on a session-only route with no per-item access
        check, so the old timestamp+basename name let any authenticated user
        reconstruct a filename and fetch media for items they can't access. A
        random token makes the URL a capability only held by viewers of the
        (access-controlled) description that embeds it.
        """
        decoded = secure_filename(unidecode(filename)).lower().rsplit(".", 1)
        suffix = f".{decoded[1]}" if len(decoded) == 2 and decoded[1] else ""
        return f"{secrets.token_urlsafe(24)}{suffix}"

    @staticmethod
    def validate_file_extension(filepath: str, allowed_extensions: list[str]) -> bool:
        """
        Validate file extension against a list of allowed extensions.

        Args:
            - filepath: the path to the file.
            - allowed_extensions: list of allowed file extensions.

        Returns:
            - True if extension is valid, False otherwise.
        """
        extension = pathlib.Path(filepath).suffix.lower().lstrip(".")
        return extension in allowed_extensions


# Structure is copied over from previous system
