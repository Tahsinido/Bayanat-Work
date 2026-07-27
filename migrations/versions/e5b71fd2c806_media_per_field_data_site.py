"""field data: allow media to be attached to an individual site

Adds media.field_data_site_id so photos and documents can be filed against a
specific site within a location, alongside the existing location-level media.

Hand-written for the same reason as the earlier field data migrations:
autogenerate produces a large spurious diff against a create-db-built database.

Revision ID: e5b71fd2c806
Revises: d4a8b2c61e93
Create Date: 2026-07-26

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "e5b71fd2c806"
down_revision = "d4a8b2c61e93"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("media", sa.Column("field_data_site_id", sa.Integer(), nullable=True))
    op.create_index("ix_media_field_data_site_id", "media", ["field_data_site_id"])
    op.create_foreign_key(
        "fk_media_field_data_site_id",
        "media",
        "field_data_site",
        ["field_data_site_id"],
        ["id"],
    )


def downgrade():
    op.drop_constraint("fk_media_field_data_site_id", "media", type_="foreignkey")
    op.drop_index("ix_media_field_data_site_id", table_name="media")
    op.drop_column("media", "field_data_site_id")
