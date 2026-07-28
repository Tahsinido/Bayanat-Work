"""missing persons, field data locations, and bulletin data folder

Three additions:
  - missing_person: a reported missing person, the interview code the report
    came from, the family contact, and free-form notes.
  - field_data_locations: links a field data location to the shared Location
    entity, the same way bulletin_locations does for bulletins.
  - bulletin.external_link: path to the folder holding a bulletin's bulk data
    outside Bayanat.

Hand-written for the same reason as the earlier field data migrations:
autogenerate produces a large spurious diff against a create-db-built database.

Revision ID: f6c93a04b1d7
Revises: e5b71fd2c806
Create Date: 2026-07-27

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "f6c93a04b1d7"
down_revision = "e5b71fd2c806"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "missing_person",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("interview_code", sa.String(), nullable=True),
        sa.Column("family_member_name", sa.String(), nullable=True),
        sa.Column("family_phone", sa.String(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("modified_last_by", sa.String(), nullable=True),
        sa.Column("modified_last_date", sa.DateTime(), nullable=True),
        # inherited from BaseMixin
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_missing_person_name", "missing_person", ["name"])
    op.create_index("ix_missing_person_interview_code", "missing_person", ["interview_code"])
    op.create_index(
        "ix_missing_person_family_member_name", "missing_person", ["family_member_name"]
    )

    op.create_table(
        "field_data_locations",
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column("field_data_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["location_id"], ["location.id"]),
        sa.ForeignKeyConstraint(["field_data_id"], ["field_data.id"]),
        sa.PrimaryKeyConstraint("location_id", "field_data_id"),
    )
    op.create_index(
        "ix_field_data_locations_location_id", "field_data_locations", ["location_id"]
    )
    op.create_index(
        "ix_field_data_locations_field_data_id", "field_data_locations", ["field_data_id"]
    )

    op.add_column("bulletin", sa.Column("external_link", sa.String(), nullable=True))


def downgrade():
    op.drop_column("bulletin", "external_link")
    op.drop_table("field_data_locations")
    op.drop_table("missing_person")
