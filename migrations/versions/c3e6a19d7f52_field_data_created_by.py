"""field data: created_by, and normalise media file types to MIME

Adds field_data.created_by (shown as "Created by" in the list) and backfills it
from modified_last_by for rows created before the column existed.

Also normalises media.media_file_type for field data media: the first version
of the upload form stored a bare extension ("pdf"), but the shared media
viewers resolve their renderer from a MIME type, so those rows would render as
"unknown". Only rows attached to field_data are touched.

Revision ID: c3e6a19d7f52
Revises: b2d5f88c3e40
Create Date: 2026-07-26

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "c3e6a19d7f52"
down_revision = "b2d5f88c3e40"
branch_labels = None
depends_on = None

EXT_TO_MIME = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "txt": "text/plain",
    "mp4": "video/mp4",
    "webm": "video/webm",
}


def upgrade():
    op.add_column("field_data", sa.Column("created_by", sa.String(), nullable=True))

    # Existing rows predate the column; the last editor is the best available
    # attribution and is correct for rows only ever touched by their author.
    op.execute("UPDATE field_data SET created_by = modified_last_by WHERE created_by IS NULL")

    for ext, mime in EXT_TO_MIME.items():
        op.execute(
            sa.text(
                "UPDATE media SET media_file_type = :mime "
                "WHERE field_data_id IS NOT NULL AND lower(media_file_type) = :ext"
            ).bindparams(mime=mime, ext=ext)
        )


def downgrade():
    op.drop_column("field_data", "created_by")
