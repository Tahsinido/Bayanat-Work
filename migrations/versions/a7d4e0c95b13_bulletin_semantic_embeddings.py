"""semantic search: store a vector per bulletin

Vectors are held as raw float32 bytes rather than a pgvector column: the image
this project ships (postgis/postgis:16-3.5) does not include pgvector, and
swapping it would mean rebuilding the database container. Scoring happens in
process over a numpy matrix, which is fast well past the current corpus size.
Moving to pgvector later only touches this table.

Hand-written for the same reason as the other migrations here: autogenerate
produces a large spurious diff against a create-db-built database.

Revision ID: a7d4e0c95b13
Revises: f6c93a04b1d7
Create Date: 2026-07-29

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a7d4e0c95b13"
down_revision = "f6c93a04b1d7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "bulletin_embedding",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bulletin_id", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("dim", sa.Integer(), nullable=False),
        sa.Column("vector", sa.LargeBinary(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        # inherited from BaseMixin
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.ForeignKeyConstraint(["bulletin_id"], ["bulletin.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bulletin_id", name="uq_bulletin_embedding_bulletin"),
    )
    op.create_index("ix_bulletin_embedding_bulletin_id", "bulletin_embedding", ["bulletin_id"])
    op.create_index("ix_bulletin_embedding_model", "bulletin_embedding", ["model"])
    op.create_index("ix_bulletin_embedding_content_hash", "bulletin_embedding", ["content_hash"])


def downgrade():
    op.drop_table("bulletin_embedding")
