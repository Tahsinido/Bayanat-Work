"""A missing person reported by a family member.

Kept deliberately small: a name, the interview the report came from, who in
the family reported it and how to reach them, plus free-form notes.
"""

import json
from typing import Any, Optional

from enferno.extensions import db
from enferno.utils.base import BaseMixin
from enferno.utils.date_helper import DateHelper
from enferno.utils.logging_utils import get_logger

logger = get_logger()

STRING_FIELDS = (
    "name",
    "interview_code",
    "family_member_name",
    "family_phone",
)


class MissingPerson(db.Model, BaseMixin):
    """SQL Alchemy model for a missing person record."""

    __tablename__ = "missing_person"
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String, index=True, nullable=False)
    # Code of the interview this report came from, as written on the interview.
    interview_code = db.Column(db.String, index=True)
    family_member_name = db.Column(db.String, index=True)
    family_phone = db.Column(db.String)
    note = db.Column(db.Text)

    # Maintained by the API, never accepted from the client. created_by is set
    # once; the modified_* pair is refreshed on every write.
    created_by = db.Column(db.String)
    modified_last_by = db.Column(db.String)
    modified_last_date = db.Column(db.DateTime)

    def from_json(self, json: dict[str, Any]) -> "MissingPerson":
        """Populate the record from a validated request payload."""
        for field in STRING_FIELDS:
            if field in json:
                value = json.get(field)
                setattr(self, field, value.strip() if isinstance(value, str) else value)

        if "note" in json:
            self.note = json.get("note")

        return self

    def stamp_modified_by(self, user: Any) -> "MissingPerson":
        """Record who last touched this row and when."""
        username = getattr(user, "username", None)
        if not self.created_by:
            self.created_by = username
        self.modified_last_by = username
        self.modified_last_date = DateHelper.utcnow()
        return self

    def delete(self, raise_exception: bool = False):
        """Soft-delete: hide the row but keep it.

        There is no revision history for this entity, so a real DELETE would be
        unrecoverable. Every read path filters deleted == False. Restore with:
            UPDATE missing_person SET deleted = false WHERE id = :id;
        """
        try:
            self.deleted = True
            db.session.add(self)
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting MissingPerson: {e}")
            if raise_exception:
                raise
            return False

    def to_dict(self) -> dict[str, Any]:
        """Return a dictionary representation of the record."""
        data = {"id": self.id, "class": self.__tablename__}
        for field in STRING_FIELDS:
            data[field] = getattr(self, field)
        data["note"] = self.note
        data["created_by"] = self.created_by
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
            "name": self.name,
            "interview_code": self.interview_code,
        }

    def __repr__(self) -> str:
        return "<MissingPerson {} {}>".format(self.id, self.name)

    def to_json(self) -> str:
        """Return a JSON representation of the record."""
        return json.dumps(self.to_dict())

    @staticmethod
    def find_by_interview_code(code: str) -> Optional["MissingPerson"]:
        """Find a record by the interview code it was reported in."""
        return MissingPerson.query.filter(MissingPerson.interview_code.ilike(code)).first()
