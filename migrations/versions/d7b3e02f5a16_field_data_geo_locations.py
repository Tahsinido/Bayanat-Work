"""map markers and site coordinates for field data

Two additions, both nullable so existing rows are untouched:

`geo_location.field_data_id` lets a field data record own map markers out of the
same table Bulletin uses. Reusing the table rather than adding coordinates to
field_data keeps one marker shape across the app -- title, type, main flag,
comment and a PostGIS point -- and keeps field markers reachable by the spatial
queries already written against geo_location.

`field_data_site.latitude` / `.longitude` give each site under a location its
own reading. Separate graves or buildings sit metres apart, so the parent
location's markers are often not precise enough for the site itself. Plain
floats rather than a PostGIS point, matching how Eyewitness stores its capture
coordinates; the parent record is where the spatial structure lives.

Hand-written for the same reason as the other migrations here: autogenerate
produces a large spurious diff against a create-db-built database.

Revision ID: d7b3e02f5a16
Revises: c1a9e73b40f8
Create Date: 2026-08-23

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "d7b3e02f5a16"
down_revision = "c1a9e73b40f8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("geo_location", sa.Column("field_data_id", sa.Integer(), nullable=True))
    op.create_index(
        "ix_geo_location_field_data_id", "geo_location", ["field_data_id"]
    )
    op.create_foreign_key(
        "fk_geo_location_field_data_id",
        "geo_location",
        "field_data",
        ["field_data_id"],
        ["id"],
    )

    op.add_column("field_data_site", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("field_data_site", sa.Column("longitude", sa.Float(), nullable=True))


def downgrade():
    op.drop_column("field_data_site", "longitude")
    op.drop_column("field_data_site", "latitude")

    op.drop_constraint("fk_geo_location_field_data_id", "geo_location", type_="foreignkey")
    op.drop_index("ix_geo_location_field_data_id", table_name="geo_location")
    op.drop_column("geo_location", "field_data_id")
