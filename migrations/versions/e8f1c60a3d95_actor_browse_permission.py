"""actor browse permission

Adds `user.can_browse_actors`, the counterpart to `can_browse_bulletins` from
c1a9e73b40f8. Each record type carries its own permission so a researcher can be
allowed to browse actors without also being handed the bulletin archive.

Deliberately false for every existing row, including the server default. Like
the bulletin one this is a tightening: after it runs a non-Admin user can still
search actors and open what their search returns, but paging through the whole
table becomes a granted privilege. Admins are unaffected -- the check
short-circuits on the Admin role and never reads this column for them.

Hand-written for the same reason as the other migrations here: autogenerate
produces a large spurious diff against a create-db-built database.

Revision ID: e8f1c60a3d95
Revises: d7b3e02f5a16
Create Date: 2026-08-23

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "e8f1c60a3d95"
down_revision = "d7b3e02f5a16"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "user",
        sa.Column(
            "can_browse_actors",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade():
    op.drop_column("user", "can_browse_actors")
