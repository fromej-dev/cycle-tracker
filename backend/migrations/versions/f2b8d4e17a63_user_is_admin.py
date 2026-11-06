"""Admin flag on users

Revision ID: f2b8d4e17a63
Revises: e6a3c7d94f21
Create Date: 2026-11-06 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "f2b8d4e17a63"
down_revision = "e6a3c7d94f21"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_admin", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )


def downgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("is_admin")
