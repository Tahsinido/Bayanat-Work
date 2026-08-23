"""evidence management: records, chain of custody, revisions, media linkage

Adds the data layer for the Evidence module:

  evidence            metadata describing an item of evidence
  evidence_custody    chain of custody, one append-only row per event
  evidence_history    field-level revisions, mirroring bulletin_history
  evidence_*          join tables to bulletins, actors, locations, events,
                      sources, access roles, and other evidence
  media.evidence_id   attaches a file to an evidence record
  media.*             evidentiary metadata on media items

FIELD NAMES ARE A DRAFT. They were derived from the summary field list in the
request, because the authoritative Evidence document was not available. Nothing
here has been renamed or merged relative to that summary, but terminology should
be reconciled against the real document before this table holds production data
-- renaming columns afterwards means a second migration over live evidence.

The evidence file itself is never stored in these tables. Files remain in Media
rows pointing back via media.evidence_id, so a file is not duplicated when it is
linked, and the metadata/content separation the specification asks for is
structural rather than conventional.

Custody has no update path by design: a mistake is corrected by appending a
Correction row, not by editing history.

Hand-written for the same reason as the other migrations here: autogenerate
produces a large spurious diff against a create-db-built database.

Revision ID: e2b5f91c3d47
Revises: d1a7c04b9e63
Create Date: 2026-08-11

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "e2b5f91c3d47"
down_revision = "d1a7c04b9e63"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "evidence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("evidence_number", sa.String(), nullable=False),
        sa.Column("evidence_type", sa.String(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("content_summary", sa.Text(), nullable=True),
        sa.Column("source_information", sa.Text(), nullable=True),
        sa.Column("ownership_information", sa.Text(), nullable=True),
        sa.Column("evidence_date", sa.DateTime(), nullable=True),
        sa.Column("date_collected", sa.DateTime(), nullable=True),
        sa.Column("collection_information", sa.Text(), nullable=True),
        sa.Column("collector", sa.String(), nullable=True),
        sa.Column("collected_by_id", sa.Integer(), nullable=True),
        sa.Column("collection_location_id", sa.Integer(), nullable=True),
        sa.Column("consent_status", sa.String(), nullable=True),
        sa.Column("consent_information", sa.Text(), nullable=True),
        sa.Column("relevance", sa.Text(), nullable=True),
        sa.Column("verification_information", sa.Text(), nullable=True),
        sa.Column("confidentiality", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("assigned_to_id", sa.Integer(), nullable=True),
        # inherited from BaseMixin
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.ForeignKeyConstraint(["collected_by_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["collection_location_id"], ["location.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["assigned_to_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("evidence_number", name="uq_evidence_number"),
    )
    op.create_index("ix_evidence_evidence_number", "evidence", ["evidence_number"])
    op.create_index("ix_evidence_evidence_type", "evidence", ["evidence_type"])
    op.create_index("ix_evidence_status", "evidence", ["status"])
    op.create_index("ix_evidence_confidentiality", "evidence", ["confidentiality"])
    op.create_index("ix_evidence_evidence_date", "evidence", ["evidence_date"])
    op.create_index("ix_evidence_date_collected", "evidence", ["date_collected"])

    op.create_table(
        "evidence_custody",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("evidence_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("handled_by", sa.String(), nullable=True),
        sa.Column("recorded_by_id", sa.Integer(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=True),
        sa.Column("location", sa.String(), nullable=True),
        sa.Column("received_from", sa.String(), nullable=True),
        sa.Column("transferred_to", sa.String(), nullable=True),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("storage_location", sa.String(), nullable=True),
        sa.Column("condition", sa.Text(), nullable=True),
        sa.Column("reference", sa.String(), nullable=True),
        sa.Column("document_media_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recorded_by_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["document_media_id"], ["media.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidence_custody_evidence_id", "evidence_custody", ["evidence_id"])
    op.create_index("ix_evidence_custody_action", "evidence_custody", ["action"])
    op.create_index("ix_evidence_custody_occurred_at", "evidence_custody", ["occurred_at"])

    op.create_table(
        "evidence_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("evidence_id", sa.Integer(), nullable=True),
        sa.Column("data", sa.JSON(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidence_history_evidence_id", "evidence_history", ["evidence_id"])

    # --- join tables ------------------------------------------------------
    joins = [
        ("evidence_roles", "role_id", "role"),
        ("evidence_bulletins", "bulletin_id", "bulletin"),
        ("evidence_actors", "actor_id", "actor"),
        ("evidence_locations", "location_id", "location"),
        ("evidence_events", "event_id", "event"),
        ("evidence_sources", "source_id", "source"),
    ]
    for table, col, target in joins:
        op.create_table(
            table,
            sa.Column("evidence_id", sa.Integer(), nullable=False),
            sa.Column(col, sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["evidence_id"], ["evidence.id"]),
            sa.ForeignKeyConstraint([col], [f"{target}.id"]),
            sa.PrimaryKeyConstraint("evidence_id", col),
        )
        op.create_index(f"ix_{table}_evidence_id", table, ["evidence_id"])
        op.create_index(f"ix_{table}_{col}", table, [col])

    # Evidence linked to other evidence; both sides point at the same table.
    op.create_table(
        "evidence_related",
        sa.Column("evidence_id", sa.Integer(), nullable=False),
        sa.Column("related_evidence_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence.id"]),
        sa.ForeignKeyConstraint(["related_evidence_id"], ["evidence.id"]),
        sa.PrimaryKeyConstraint("evidence_id", "related_evidence_id"),
    )
    op.create_index("ix_evidence_related_evidence_id", "evidence_related", ["evidence_id"])
    op.create_index("ix_evidence_related_related_id", "evidence_related", ["related_evidence_id"])

    # --- media: evidence linkage and evidentiary metadata -----------------
    op.add_column("media", sa.Column("evidence_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_media_evidence_id", "media", "evidence", ["evidence_id"], ["id"], ondelete="CASCADE"
    )
    op.create_index("ix_media_evidence_id", "media", ["evidence_id"])

    op.add_column("media", sa.Column("media_number", sa.String(), nullable=True))
    op.create_index("ix_media_media_number", "media", ["media_number"], unique=True)

    op.add_column("media", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("media", sa.Column("date_recorded", sa.DateTime(), nullable=True))
    op.add_column("media", sa.Column("date_obtained", sa.DateTime(), nullable=True))
    op.add_column("media", sa.Column("location_id", sa.Integer(), nullable=True))
    op.add_column("media", sa.Column("source_id", sa.Integer(), nullable=True))
    op.add_column("media", sa.Column("creator", sa.String(), nullable=True))
    op.add_column("media", sa.Column("person_actor_id", sa.Integer(), nullable=True))
    op.add_column("media", sa.Column("event_id", sa.Integer(), nullable=True))
    op.add_column("media", sa.Column("relevance", sa.Text(), nullable=True))
    op.add_column("media", sa.Column("confidentiality", sa.String(), nullable=True))
    op.add_column("media", sa.Column("consent_status", sa.String(), nullable=True))
    op.add_column("media", sa.Column("custody_reference", sa.String(), nullable=True))
    op.add_column("media", sa.Column("version", sa.Integer(), server_default="1", nullable=True))
    op.add_column("media", sa.Column("status", sa.String(), nullable=True))
    op.add_column("media", sa.Column("notes", sa.Text(), nullable=True))

    op.create_foreign_key("fk_media_location_id", "media", "location", ["location_id"], ["id"])
    op.create_foreign_key("fk_media_source_id", "media", "source", ["source_id"], ["id"])
    op.create_foreign_key("fk_media_person_actor_id", "media", "actor", ["person_actor_id"], ["id"])
    op.create_foreign_key("fk_media_event_id", "media", "event", ["event_id"], ["id"])
    op.create_index("ix_media_confidentiality", "media", ["confidentiality"])
    op.create_index("ix_media_status", "media", ["status"])


def downgrade():
    op.drop_index("ix_media_status", table_name="media")
    op.drop_index("ix_media_confidentiality", table_name="media")
    op.drop_constraint("fk_media_event_id", "media", type_="foreignkey")
    op.drop_constraint("fk_media_person_actor_id", "media", type_="foreignkey")
    op.drop_constraint("fk_media_source_id", "media", type_="foreignkey")
    op.drop_constraint("fk_media_location_id", "media", type_="foreignkey")

    for col in (
        "notes",
        "status",
        "version",
        "custody_reference",
        "consent_status",
        "confidentiality",
        "relevance",
        "event_id",
        "person_actor_id",
        "creator",
        "source_id",
        "location_id",
        "date_obtained",
        "date_recorded",
        "description",
    ):
        op.drop_column("media", col)

    op.drop_index("ix_media_media_number", table_name="media")
    op.drop_column("media", "media_number")

    op.drop_index("ix_media_evidence_id", table_name="media")
    op.drop_constraint("fk_media_evidence_id", "media", type_="foreignkey")
    op.drop_column("media", "evidence_id")

    op.drop_table("evidence_related")
    for table in (
        "evidence_sources",
        "evidence_events",
        "evidence_locations",
        "evidence_actors",
        "evidence_bulletins",
        "evidence_roles",
    ):
        op.drop_table(table)

    op.drop_table("evidence_history")
    op.drop_table("evidence_custody")
    op.drop_table("evidence")
