"""merge the three divergent migration heads

Three features branched from the same point and were never rejoined:

  c7d2e9f4a1b8  eventtype.for_incident
  68396035f041  media_redaction.original_media_id
  c9f4b6d18a72  download approval and verification codes

Alembic refuses to resolve "head" while more than one exists, so both
`flask db upgrade` and `flask db stamp head` fail with "Multiple head revisions
are present". flask/bin/entrypoint.sh runs those on startup under `set -e`, so
the container exits before the app comes up.

This revision has no schema of its own -- it exists purely to give the three
branches a single descendant so "head" is unambiguous again.

Revision ID: d1a7c04b9e63
Revises: c7d2e9f4a1b8, 68396035f041, c9f4b6d18a72
Create Date: 2026-08-11

"""

# revision identifiers, used by Alembic.
revision = "d1a7c04b9e63"
down_revision = ("c7d2e9f4a1b8", "68396035f041", "c9f4b6d18a72")
branch_labels = None
depends_on = None


def upgrade():
    """No-op: merge points carry no schema change."""
    pass


def downgrade():
    """No-op: splitting back into three heads needs no schema change."""
    pass
