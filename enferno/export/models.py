from datetime import datetime as dt
from pathlib import Path
from typing import Any, Union

import arrow
from sqlalchemy import ARRAY
from flask_security.decorators import current_user

from enferno.extensions import db
from enferno.settings import Config

from enferno.utils import download_codes
from enferno.utils.base import BaseMixin
from enferno.utils.date_helper import DateHelper
from itsdangerous import URLSafeSerializer

from enferno.utils.logging_utils import get_logger

logger = get_logger()


class Export(db.Model, BaseMixin):
    export_dir = Path("enferno/exports")
    export_file_name = "export"
    signer = URLSafeSerializer(Config.get("SECRET_KEY"))
    """
    SQL Alchemy model for export table.
    """
    id = db.Column(db.Integer, primary_key=True)
    requester_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    requester = db.relationship("User", backref="user_exports", foreign_keys=[requester_id])
    items = db.Column(ARRAY(db.Integer))
    table = db.Column(db.String, nullable=False)
    file_format = db.Column(db.String, nullable=False)
    include_media = db.Column(db.Boolean, default=False)
    file_id = db.Column(db.String)
    tags = db.Column(ARRAY(db.String), nullable=False, default=[])
    comment = db.Column(db.Text)
    status = db.Column(db.String, nullable=False, default="Pending")
    approver_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    approver = db.relationship("User", backref="approved_exports", foreign_keys=[approver_id])
    expires_on = db.Column(db.DateTime)

    # Approval alone no longer releases the archive: the approving admin is
    # given a one-time code out of band, and the requester has to return it
    # before the file is served. Stored hashed -- a database dump must not be
    # enough to unlock an export.
    code_hash = db.Column(db.String)
    code_expires_on = db.Column(db.DateTime)
    code_attempts = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    downloaded_at = db.Column(db.DateTime)

    @property
    def unique_id(self):
        return Export.signer.dumps(self.id)

    @staticmethod
    def decrypt_unique_id(key: Union[str, bytes]) -> Any:
        """
        Static method to decrypt unique id.

        Args:
            - key: unique id.

        Returns:
            - export request id.
        """
        return Export.signer.loads(key)

    @property
    def expired(self):
        if self.expires_on:
            return dt.utcnow() > self.expires_on
        else:
            return True

    @staticmethod
    def _accessible_item_ids(table: str, items: Any) -> list:
        """Filter requested export item IDs to those the current user may access
        (BAY-01-026). Admins keep everything; others keep only in-scope items.
        """
        from enferno.admin.models import Actor, Bulletin, Incident

        model = {"bulletin": Bulletin, "actor": Actor, "incident": Incident}.get(table)
        if not model or not isinstance(items, list):
            return []
        rows = model.query.filter(model.id.in_(items)).all()
        allowed = {r.id for r in rows if current_user and current_user.can_access(r)}
        return [i for i in items if i in allowed]

    def from_json(self, table: str, json: dict) -> "Export":
        """
        Export Deserializer.

        Args:
            - table: str for the table the export is for
            - json: json request data

        Returns:
            - Export object
        """
        if not isinstance(json, dict):
            json = {}
        cfg = json.get("config")
        if not isinstance(cfg, dict):
            cfg = {}

        self.requester = current_user
        self.table = table
        # Store only items the requester can access (BAY-01-026): keep crafted /
        # out-of-scope IDs from ever being persisted, approved, or exported. The
        # worker re-validates access at generation time too (BAY-01-003).
        self.items = self._accessible_item_ids(table, json.get("items"))
        self.tags = cfg.get("tags", [])
        self.comment = cfg.get("comment")
        self.file_format = cfg.get("format")
        self.include_media = cfg.get("includeMedia")

        return self

    def to_dict(self) -> dict:
        """
        Export Serializer.
        """
        return {
            "id": self.id,
            "class": self.__tablename__,
            "table": self.table,
            "requester": self.requester.to_compact(),
            "approver": self.approver.to_compact() if self.approver else None,
            "include_media": self.include_media,
            "file_format": self.file_format,
            "status": self.status,
            "comment": self.comment,
            "tags": self.tags or None,
            "file_id": self.file_id,
            "expires_on": (
                DateHelper.serialize_datetime(self.expires_on) if self.expires_on else None
            ),
            "updated_at": (
                DateHelper.serialize_datetime(self.updated_at) if self.updated_at else None
            ),
            "created_at": (
                DateHelper.serialize_datetime(self.created_at) if self.created_at else None
            ),
            "expired": self.expired,
            "uid": self.unique_id,
            "items": self.items,
            # Never the code itself -- only whether one is currently usable.
            "code_required": download_codes.approval_enabled(),
            "code_expired": self.code_expired,
            "code_locked": self.code_locked,
            "downloaded_at": DateHelper.serialize_datetime(self.downloaded_at),
            "attempts_left": max(0, download_codes.max_attempts() - (self.code_attempts or 0)),
        }

    def approve(self) -> "Export":
        """
        Method to approve Export requests.
        """
        self.status = "Processing"
        # set download expiry
        self.expires_on = dt.utcnow() + Config.get("EXPORT_DEFAULT_EXPIRY")
        self.approver = current_user

        return self

    def issue_code(self) -> str:
        """Mint the one-time download code, returning the plaintext once.

        The caller shows it to the approving admin and then forgets it: only
        the hash is stored.
        """
        code = download_codes.generate_code()
        self.code_hash = download_codes.hash_code(code)
        self.code_expires_on = download_codes.code_expiry_from_now()
        self.code_attempts = 0
        self.downloaded_at = None
        return code

    @property
    def code_expired(self) -> bool:
        return bool(self.code_expires_on and dt.utcnow() > self.code_expires_on)

    @property
    def code_locked(self) -> bool:
        return (self.code_attempts or 0) >= download_codes.max_attempts()

    def verify_code(self, code: str) -> bool:
        """Check a submitted code, counting the attempt either way.

        Counting failures is what keeps a short code safe; commit after
        calling this so the counter survives.
        """
        if self.code_expired or self.code_locked or not self.code_hash:
            return False
        self.code_attempts = (self.code_attempts or 0) + 1
        return download_codes.check_code(code, self.code_hash)

    def mark_downloaded(self) -> "Export":
        """Spend the code so one approval releases the archive once."""
        self.downloaded_at = dt.utcnow()
        self.code_hash = None
        self.code_expires_on = None
        return self

    def reject(self) -> "Export":
        """
        Method to reject Export requests.
        """
        self.status = "Rejected"
        self.code_hash = None
        self.code_expires_on = None

        return self

    def set_expiry(self, date) -> "Export":
        """
        Method to change expiry date/time
        """
        try:
            expires_on = arrow.get(date)
        except Exception as e:
            logger.error(f"Error saving export #{self.id}: \n {e}")

        if expires_on > arrow.utcnow():
            self.expires_on = expires_on.format("YYYY-MM-DDTHH:mm")

        return self

    @staticmethod
    def generate_export_dir() -> str:
        """
        Static method to generate export directory.

        Returns:
            - export directory
        """
        dir_id = f'export_{dt.utcnow().strftime("%Y%m%d-%H%M%S")}'
        Path(Export.export_dir / dir_id).mkdir(parents=True, exist_ok=True)
        return dir_id

    @staticmethod
    def generate_export_file() -> tuple[Path, str]:
        """
        static method to generate export file.

        Returns:
            - export file path, export directory
        """
        # Create unique directory
        dir_id = Export.generate_export_dir()
        return Export.export_dir / dir_id / Export.export_file_name, dir_id
