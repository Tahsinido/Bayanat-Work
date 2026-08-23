"""admin-approved downloads with one-time verification codes

Taking a copy of a file off the system now needs two people: an admin approves
the request and is shown a code once, which reaches the requester out of band
and has to come back before the file is served.

Adds `download_request` for media files, and the matching code columns on
`export` so an approved archive is not released on approval alone.

Codes are stored hashed, so this migration adds no column that could release a
file if the database were read.

Hand-written for the same reason as the other migrations here: autogenerate
produces a large spurious diff against a create-db-built database.

Revision ID: c9f4b6d18a72
Revises: b8e1a3f27c94
Create Date: 2026-08-06

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "c9f4b6d18a72"
down_revision = "b8e1a3f27c94"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "download_request",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("media_id", sa.Integer(), nullable=False),
        sa.Column("requester_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="Pending"),
        sa.Column("reviewer_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("code_hash", sa.String(), nullable=True),
        sa.Column("code_expires_on", sa.DateTime(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_on", sa.DateTime(), nullable=True),
        sa.Column("fulfilled_at", sa.DateTime(), nullable=True),
        # inherited from BaseMixin
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.ForeignKeyConstraint(["media_id"], ["media.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requester_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["reviewer_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_download_request_media_id", "download_request", ["media_id"])
    op.create_index("ix_download_request_requester_id", "download_request", ["requester_id"])
    op.create_index("ix_download_request_status", "download_request", ["status"])

    op.add_column("export", sa.Column("code_hash", sa.String(), nullable=True))
    op.add_column("export", sa.Column("code_expires_on", sa.DateTime(), nullable=True))
    op.add_column(
        "export",
        sa.Column("code_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("export", sa.Column("downloaded_at", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("export", "downloaded_at")
    op.drop_column("export", "code_attempts")
    op.drop_column("export", "code_expires_on")
    op.drop_column("export", "code_hash")

    op.drop_index("ix_download_request_status", table_name="download_request")
    op.drop_index("ix_download_request_requester_id", table_name="download_request")
    op.drop_index("ix_download_request_media_id", table_name="download_request")
    op.drop_table("download_request")
