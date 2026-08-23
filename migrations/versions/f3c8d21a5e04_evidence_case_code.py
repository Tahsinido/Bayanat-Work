"""case code on evidence records

Adds `evidence.case_code`: the team's own reference for the case an exhibit
belongs to, entered by hand rather than generated. Deliberately not unique --
several exhibits routinely share one case -- but indexed, because it is the
identifier people actually search by.

Nullable with no default, so existing records are untouched and simply carry no
case code until one is typed in.

Hand-written for the same reason as the other migrations here: autogenerate
produces a large spurious diff against a create-db-built database.

Revision ID: f3c8d21a5e04
Revises: e2b5f91c3d47
Create Date: 2026-08-19

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "f3c8d21a5e04"
down_revision = "e2b5f91c3d47"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("evidence", sa.Column("case_code", sa.String(), nullable=True))
    op.create_index("ix_evidence_case_code", "evidence", ["case_code"])


def downgrade():
    op.drop_index("ix_evidence_case_code", table_name="evidence")
    op.drop_column("evidence", "case_code")
