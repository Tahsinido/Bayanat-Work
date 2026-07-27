"""field data: per-location sites and external storage links

Adds field_data_site so one location can hold several sites, each with its own
collection figures, storage details and analysis, plus field_data.external_link
for data kept outside Bayanat.

Hand-written for the same reason as the earlier field data migrations:
autogenerate produces a large spurious diff against a create-db-built database.

Revision ID: d4a8b2c61e93
Revises: c3e6a19d7f52
Create Date: 2026-07-26

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "d4a8b2c61e93"
down_revision = "c3e6a19d7f52"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("field_data", sa.Column("external_link", sa.String(), nullable=True))

    op.create_table(
        "field_data_site",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("field_data_id", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("site_name", sa.String(), nullable=False),
        sa.Column("mission_date", sa.DateTime(), nullable=True),
        sa.Column("collected_data_by", sa.String(), nullable=True),
        sa.Column("data_types", sa.ARRAY(sa.String()), nullable=True),
        sa.Column("type_of_site", sa.String(), nullable=True),
        sa.Column("no_of_site", sa.Integer(), nullable=True),
        sa.Column("code", sa.String(), nullable=True),
        sa.Column("total_photos", sa.Integer(), nullable=True),
        sa.Column("total_videos", sa.Integer(), nullable=True),
        sa.Column("total_interviews", sa.Integer(), nullable=True),
        sa.Column("translation", sa.String(), nullable=True),
        sa.Column("drone_photos", sa.Integer(), nullable=True),
        sa.Column("drone_videos", sa.Integer(), nullable=True),
        sa.Column("data_size_for_site", sa.String(), nullable=True),
        sa.Column("total_size", sa.String(), nullable=True),
        sa.Column("data_storage_location", sa.String(), nullable=True),
        sa.Column("external_link", sa.String(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("legal_analysis", sa.Text(), nullable=True),
        sa.Column("analysis_by", sa.String(), nullable=True),
        sa.Column("analysis_date", sa.DateTime(), nullable=True),
        sa.Column("shared_with", sa.String(), nullable=True),
        sa.Column("excavated_status", sa.String(), nullable=True),
        sa.Column("times_documented", sa.Integer(), nullable=True),
        sa.Column("has_interview", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("interview_names", sa.ARRAY(sa.String()), nullable=True),
        # inherited from BaseMixin
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.ForeignKeyConstraint(["field_data_id"], ["field_data.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_field_data_site_field_data_id", "field_data_site", ["field_data_id"])
    op.create_index("ix_field_data_site_site_name", "field_data_site", ["site_name"])
    op.create_index("ix_field_data_site_code", "field_data_site", ["code"])
    op.create_index("ix_field_data_site_type_of_site", "field_data_site", ["type_of_site"])
    op.create_index("ix_field_data_site_excavated_status", "field_data_site", ["excavated_status"])


def downgrade():
    op.drop_table("field_data_site")
    op.drop_column("field_data", "external_link")
