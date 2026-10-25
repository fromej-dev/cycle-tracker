"""Partner share, outgoing webhooks and Home Assistant state token

Revision ID: c4e8a1f67d02
Revises: b7d2e5a91c30
Create Date: 2026-10-27 09:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c4e8a1f67d02"
down_revision = "b7d2e5a91c30"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("partner_share_token_hash", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("partner_share_name", sa.String(length=40), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "partner_share_fertile",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "partner_share_window_days",
                sa.Integer(),
                server_default="7",
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column("ha_token_hash", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "ha_include_fertile",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column("webhook_state", sa.Text(), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_users_partner_share_token_hash"),
            ["partner_share_token_hash"],
            unique=True,
        )
        batch_op.create_index(
            batch_op.f("ix_users_ha_token_hash"), ["ha_token_hash"], unique=True
        )

    op.create_table(
        "webhooks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("events", sa.Text(), nullable=False),
        sa.Column("secret", sa.String(length=64), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("last_status", sa.Integer(), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("failures", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("webhooks", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_webhooks_user_id"), ["user_id"], unique=False
        )


def downgrade():
    with op.batch_alter_table("webhooks", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_webhooks_user_id"))
    op.drop_table("webhooks")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_ha_token_hash"))
        batch_op.drop_index(batch_op.f("ix_users_partner_share_token_hash"))
        batch_op.drop_column("webhook_state")
        batch_op.drop_column("ha_include_fertile")
        batch_op.drop_column("ha_token_hash")
        batch_op.drop_column("partner_share_window_days")
        batch_op.drop_column("partner_share_fertile")
        batch_op.drop_column("partner_share_name")
        batch_op.drop_column("partner_share_token_hash")
