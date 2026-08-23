"""eyewitness GPS coordinates and field-data link

Adds `latitude`/`longitude` to a capture, and the join to field-data site
visits.

The coordinates sit alongside the linked location rather than replacing it: the
location places the capture in the archive's own geography, the reading says
where the device actually was, and those are two different claims.

Hand-written for the same reason as the other migrations here: autogenerate
produces a large spurious diff against a create-db-built database.

Revision ID: b5d1f8c62a94
Revises: a7e4b93c150d
Create Date: 2026-08-19

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "b5d1f8c62a94"
down_revision = "a7e4b93c150d"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("eyewitness", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("eyewitness", sa.Column("longitude", sa.Float(), nullable=True))

    op.create_table(
        "eyewitness_field_data",
        sa.Column("eyewitness_id", sa.Integer(), nullable=False),
        sa.Column("field_data_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["eyewitness_id"], ["eyewitness.id"]),
        sa.ForeignKeyConstraint(["field_data_id"], ["field_data.id"]),
        sa.PrimaryKeyConstraint("eyewitness_id", "field_data_id"),
    )
    op.create_index(
        "ix_eyewitness_field_data_eyewitness_id", "eyewitness_field_data", ["eyewitness_id"]
    )
    op.create_index(
        "ix_eyewitness_field_data_field_data_id", "eyewitness_field_data", ["field_data_id"]
    )


def downgrade():
    op.drop_table("eyewitness_field_data")
    op.drop_column("eyewitness", "longitude")
    op.drop_column("eyewitness", "latitude")
