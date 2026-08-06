"""semantic search: one embedding row per passage instead of per bulletin

The embedding model has a fixed input window (128 tokens for the shipped
paraphrase-multilingual-MiniLM-L12-v2). Storing one vector per bulletin meant
everything past that window was silently dropped, and because the searchable
text starts with four title fields, that cut the description short and lost
every field after it, attachment OCR text included.

A bulletin now owns one row per chunk, so every field lands inside some window,
and each row carries the passage it was built from so a match can be explained
without re-embedding anything at query time.

Existing rows are left in place but are stale: they hold a truncated vector and
no chunk text. Run `flask reindex-semantic --force` after upgrading to rebuild
them. Search keeps working on the old rows until then, just without the
description coverage this migration exists to fix.

Hand-written for the same reason as the other migrations here: autogenerate
produces a large spurious diff against a create-db-built database.

Revision ID: b8e1a3f27c94
Revises: a7d4e0c95b13
Create Date: 2026-08-06

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "b8e1a3f27c94"
down_revision = "a7d4e0c95b13"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "bulletin_embedding",
        sa.Column("chunk_index", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("bulletin_embedding", sa.Column("chunk_text", sa.Text(), nullable=True))

    # One row per bulletin was the whole point of this constraint; a bulletin
    # now owns one row per chunk.
    op.drop_constraint("uq_bulletin_embedding_bulletin", "bulletin_embedding", type_="unique")
    op.create_unique_constraint(
        "uq_bulletin_embedding_chunk",
        "bulletin_embedding",
        ["bulletin_id", "model", "chunk_index"],
    )


def downgrade():
    # Collapsing back to one row per bulletin has to discard the extra chunks,
    # otherwise the unique constraint cannot be restored.
    op.execute("DELETE FROM bulletin_embedding WHERE chunk_index <> 0")
    op.drop_constraint("uq_bulletin_embedding_chunk", "bulletin_embedding", type_="unique")
    op.create_unique_constraint(
        "uq_bulletin_embedding_bulletin", "bulletin_embedding", ["bulletin_id"]
    )
    op.drop_column("bulletin_embedding", "chunk_text")
    op.drop_column("bulletin_embedding", "chunk_index")
