"""Per-feed random secret for opaque calendar event UIDs

Revision ID: b7d2e5a91c30
Revises: a3f1c9d2b7e4
Create Date: 2026-10-26 09:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b7d2e5a91c30"
down_revision = "a3f1c9d2b7e4"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("calendar_uid_key", sa.String(length=64), nullable=True)
        )


def downgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("calendar_uid_key")
