"""Partner share show_current + hysteresis memory; webhook disabled_reason

Revision ID: d5f9b2c83e17
Revises: c4e8a1f67d02
Create Date: 2026-10-28 09:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "d5f9b2c83e17"
down_revision = "c4e8a1f67d02"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "partner_share_show_current",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column("heads_up_state", sa.Text(), nullable=True))
    with op.batch_alter_table("webhooks", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("disabled_reason", sa.String(length=200), nullable=True)
        )


def downgrade():
    with op.batch_alter_table("webhooks", schema=None) as batch_op:
        batch_op.drop_column("disabled_reason")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("heads_up_state")
        batch_op.drop_column("partner_share_show_current")
