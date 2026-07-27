"""field data: description, documentation count, interviews and media

Adds the narrative/description column, the documentation counter, the
interview flag plus names, and the media.field_data_id foreign key that lets
media files be attached to a field data record.

Hand-written for the same reason as a1c4e77b2d19: autogenerate produces a large
spurious diff against a create-db-built database.

Revision ID: b2d5f88c3e40
Revises: a1c4e77b2d19
Create Date: 2026-07-26

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "b2d5f88c3e40"
down_revision = "a1c4e77b2d19"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("field_data", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("field_data", sa.Column("times_documented", sa.Integer(), nullable=True))
    op.add_column(
        "field_data",
        sa.Column("has_interview", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column("field_data", sa.Column("interview_names", sa.ARRAY(sa.String()), nullable=True))

    op.add_column("media", sa.Column("field_data_id", sa.Integer(), nullable=True))
    op.create_index("ix_media_field_data_id", "media", ["field_data_id"])
    op.create_foreign_key(
        "fk_media_field_data_id", "media", "field_data", ["field_data_id"], ["id"]
    )


def downgrade():
    op.drop_constraint("fk_media_field_data_id", "media", type_="foreignkey")
    op.drop_index("ix_media_field_data_id", table_name="media")
    op.drop_column("media", "field_data_id")

    op.drop_column("field_data", "interview_names")
    op.drop_column("field_data", "has_interview")
    op.drop_column("field_data", "times_documented")
    op.drop_column("field_data", "description")
