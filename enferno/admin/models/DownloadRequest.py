"""A user's request to download an original media file.

Viewing media is unchanged: thumbnails, video playback and PDF preview keep
serving straight from the media routes. Taking a *copy* of the original file off
the system is what this gates -- an admin has to approve it, and the requester
then has to prove they received the code the admin issued out of band.

Each request covers one file for one person and is spent on first use, so an
approval cannot be replayed later or shared with someone else.
"""

from typing import Any

from enferno.extensions import db
from enferno.utils.base import BaseMixin
from enferno.utils.date_helper import DateHelper
from enferno.utils.logging_utils import get_logger
from enferno.utils import download_codes

logger = get_logger()


class DownloadRequest(db.Model, BaseMixin):
    """SQL Alchemy model for a gated media download."""

    __tablename__ = "download_request"
    __table_args__ = {"extend_existing": True}

    STATUS_PENDING = "Pending"
    STATUS_APPROVED = "Approved"
    STATUS_REJECTED = "Rejected"
    STATUS_FULFILLED = "Fulfilled"

    id = db.Column(db.Integer, primary_key=True)

    media_id = db.Column(
        db.Integer,
        db.ForeignKey("media.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    media = db.relationship("Media", backref=db.backref("download_requests", lazy="dynamic"))

    requester_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True, nullable=False)
    requester = db.relationship("User", foreign_keys=[requester_id])

    # Why the file is needed. Recorded for the audit trail rather than checked
    # by anything: an approval decision needs a stated purpose behind it.
    reason = db.Column(db.Text)

    status = db.Column(db.String, nullable=False, default=STATUS_PENDING, index=True)

    reviewer_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    reviewer = db.relationship("User", foreign_keys=[reviewer_id])
    reviewed_at = db.Column(db.DateTime)

    # Hashed, never plaintext: a database dump must not unlock any download.
    code_hash = db.Column(db.String)
    code_expires_on = db.Column(db.DateTime)
    attempts = db.Column(db.Integer, nullable=False, default=0)

    # When the approval itself stops being usable, separate from the much
    # shorter life of the code.
    expires_on = db.Column(db.DateTime)
    fulfilled_at = db.Column(db.DateTime)

    @property
    def expired(self) -> bool:
        """True once the approval is too old to use."""
        return bool(self.expires_on and DateHelper.utcnow() > self.expires_on)

    @property
    def code_expired(self) -> bool:
        """True once the issued code is too old to use."""
        return bool(self.code_expires_on and DateHelper.utcnow() > self.code_expires_on)

    @property
    def locked(self) -> bool:
        """True once too many wrong codes have been tried."""
        return (self.attempts or 0) >= download_codes.max_attempts()

    @property
    def downloadable(self) -> bool:
        """Whether a correct code would currently release the file."""
        return (
            self.status == self.STATUS_APPROVED
            and not self.expired
            and not self.code_expired
            and not self.locked
        )

    def approve(self, reviewer) -> str:
        """Approve and mint a code, returning the plaintext exactly once.

        The caller is responsible for showing it to the approving admin and
        then forgetting it -- only the hash is kept here.
        """
        code = download_codes.generate_code()
        self.status = self.STATUS_APPROVED
        self.reviewer_id = getattr(reviewer, "id", None)
        self.reviewed_at = DateHelper.utcnow()
        self.code_hash = download_codes.hash_code(code)
        self.code_expires_on = download_codes.code_expiry_from_now()
        self.expires_on = download_codes.request_expiry_from_now()
        self.attempts = 0
        self.fulfilled_at = None
        return code

    def reject(self, reviewer) -> "DownloadRequest":
        """Reject the request and destroy any code already issued."""
        self.status = self.STATUS_REJECTED
        self.reviewer_id = getattr(reviewer, "id", None)
        self.reviewed_at = DateHelper.utcnow()
        self.code_hash = None
        self.code_expires_on = None
        return self

    def verify(self, code: str) -> bool:
        """Check a submitted code, counting the attempt either way.

        Counting failures is what makes the short code safe; the counter is the
        caller's to persist, so commit after calling this.
        """
        if not self.downloadable:
            return False
        self.attempts = (self.attempts or 0) + 1
        if not download_codes.check_code(code, self.code_hash):
            return False
        return True

    def fulfill(self) -> "DownloadRequest":
        """Spend the request so the approval cannot be reused."""
        self.status = self.STATUS_FULFILLED
        self.fulfilled_at = DateHelper.utcnow()
        self.code_hash = None
        self.code_expires_on = None
        return self

    def to_dict(self, include_media: bool = True) -> dict[str, Any]:
        data = {
            "id": self.id,
            "media_id": self.media_id,
            "status": self.status,
            "reason": self.reason,
            "requester": self.requester.to_compact() if self.requester else None,
            "reviewer": self.reviewer.to_compact() if self.reviewer else None,
            "reviewed_at": DateHelper.serialize_datetime(self.reviewed_at),
            "created_at": DateHelper.serialize_datetime(self.created_at),
            "expires_on": DateHelper.serialize_datetime(self.expires_on),
            "code_expires_on": DateHelper.serialize_datetime(self.code_expires_on),
            "fulfilled_at": DateHelper.serialize_datetime(self.fulfilled_at),
            "expired": self.expired,
            "code_expired": self.code_expired,
            "locked": self.locked,
            "downloadable": self.downloadable,
            "attempts_left": max(0, download_codes.max_attempts() - (self.attempts or 0)),
        }
        if include_media and self.media:
            data["media"] = {
                "id": self.media.id,
                "title": self.media.title,
                "filename": self.media.media_file,
            }
        return data

    def to_mini(self) -> dict[str, Any]:
        """Snapshot for the activity log.

        Carries the filename and the record the file hangs off, not just ids:
        an audit trail that reads "download_request 41" answers nothing, and by
        the time anyone reads it the row may be gone.
        """
        media = self.media
        data = {
            "id": self.id,
            "class": "download_request",
            "media_id": self.media_id,
            "filename": media.media_file if media else None,
            "title": (media.title if media else None) or None,
            "status": self.status,
            "requester_id": self.requester_id,
        }
        # Where the file lives, so a reviewer can open the surrounding record.
        if media is not None:
            if media.bulletin_id:
                data["parent_class"] = "bulletin"
                data["parent_id"] = media.bulletin_id
            elif media.actor_id:
                data["parent_class"] = "actor"
                data["parent_id"] = media.actor_id
        return data

    def __repr__(self) -> str:
        return f"<DownloadRequest {self.id} media={self.media_id} status={self.status}>"
