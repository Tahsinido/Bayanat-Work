"""eyewitness capture records

Adds the `eyewitness` table and its joins. A capture holds what the device and
the person recorded -- item, count, device, username, account of the event,
notes, when and where -- and links out to the entities Bayanat already models
rather than restating them.

District and governorate get no columns: they are read from the captured
location's own admin hierarchy, so they cannot contradict it.

`media.eyewitness_id` lets a raw recording hang off the capture without being
implicitly promoted to evidence.

Hand-written for the same reason as the other migrations here: autogenerate
produces a large spurious diff against a create-db-built database.

Revision ID: a7e4b93c150d
Revises: f3c8d21a5e04
Create Date: 2026-08-19

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a7e4b93c150d"
down_revision = "f3c8d21a5e04"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "eyewitness",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.String(), nullable=True),
        sa.Column("number_of_items", sa.Integer(), nullable=True),
        sa.Column("device_id", sa.String(), nullable=True),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("alleged_event_id", sa.Integer(), nullable=True),
        sa.Column("event_description", sa.Text(), nullable=True),
        sa.Column("user_notes", sa.Text(), nullable=True),
        sa.Column("date_of_capture", sa.DateTime(), nullable=True),
        sa.Column("capture_location_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("assigned_to_id", sa.Integer(), nullable=True),
        sa.Column("deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["alleged_event_id"], ["event.id"]),
        sa.ForeignKeyConstraint(["capture_location_id"], ["location.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["assigned_to_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for col in ("item_id", "device_id", "username", "date_of_capture", "status"):
        op.create_index(f"ix_eyewitness_{col}", "eyewitness", [col])
    op.create_index("ix_eyewitness_alleged_event_id", "eyewitness", ["alleged_event_id"])
    op.create_index("ix_eyewitness_capture_location_id", "eyewitness", ["capture_location_id"])

    joins = (
        ("eyewitness_roles", "role_id", "role.id"),
        ("eyewitness_bulletins", "bulletin_id", "bulletin.id"),
        ("eyewitness_actors", "actor_id", "actor.id"),
        ("eyewitness_labels", "label_id", "label.id"),
        ("eyewitness_evidence", "evidence_id", "evidence.id"),
    )
    for table, other_col, target in joins:
        op.create_table(
            table,
            sa.Column("eyewitness_id", sa.Integer(), nullable=False),
            sa.Column(other_col, sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["eyewitness_id"], ["eyewitness.id"]),
            sa.ForeignKeyConstraint([other_col], [target]),
            sa.PrimaryKeyConstraint("eyewitness_id", other_col),
        )
        op.create_index(f"ix_{table}_eyewitness_id", table, ["eyewitness_id"])
        op.create_index(f"ix_{table}_{other_col}", table, [other_col])

    op.add_column("media", sa.Column("eyewitness_id", sa.Integer(), nullable=True))
    op.create_index("ix_media_eyewitness_id", "media", ["eyewitness_id"])
    op.create_foreign_key(
        "fk_media_eyewitness_id", "media", "eyewitness", ["eyewitness_id"], ["id"], ondelete="CASCADE"
    )


def downgrade():
    op.drop_constraint("fk_media_eyewitness_id", "media", type_="foreignkey")
    op.drop_index("ix_media_eyewitness_id", table_name="media")
    op.drop_column("media", "eyewitness_id")

    for table in (
        "eyewitness_evidence",
        "eyewitness_labels",
        "eyewitness_actors",
        "eyewitness_bulletins",
        "eyewitness_roles",
    ):
        op.drop_table(table)

    op.drop_table("eyewitness")
