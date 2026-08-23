"""bulletin browse permission

Adds `user.can_browse_bulletins`: whether a user may list bulletins without
searching first. Sits alongside the other per-user abilities (can_export,
can_access_media, can_self_assign) and is granted the same way.

Deliberately false for every existing row, including the server default. This
migration is a tightening: after it runs, a non-Admin user can still search
bulletins and open what their search returns, but paging through the whole table
becomes a granted privilege rather than the default. Admins are unaffected --
the check short-circuits on the Admin role and never reads this column for them.

Grant it back to the staff who need it in User Management once the migration has
run.

Hand-written for the same reason as the other migrations here: autogenerate
produces a large spurious diff against a create-db-built database.

Revision ID: c1a9e73b40f8
Revises: b5d1f8c62a94
Create Date: 2026-08-23

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "c1a9e73b40f8"
down_revision = "b5d1f8c62a94"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "user",
        sa.Column(
            "can_browse_bulletins",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade():
    op.drop_column("user", "can_browse_bulletins")
