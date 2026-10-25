"""Planned events (date check) and private calendar feed columns

Revision ID: a3f1c9d2b7e4
Revises: 376d034c3243
Create Date: 2026-10-25 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a3f1c9d2b7e4"
down_revision = "376d034c3243"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "planned_events",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("planned_events", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_planned_events_user_id"), ["user_id"], unique=False
        )

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("calendar_token_hash", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("calendar_label", sa.String(length=40), nullable=True)
        )
        batch_op.add_column(
            sa.Column("calendar_fertile_label", sa.String(length=40), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "calendar_mark_estimate",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column("calendar_timezone", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(sa.Column("calendar_state", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "calendar_include_fertile",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )
        batch_op.create_index(
            batch_op.f("ix_users_calendar_token_hash"),
            ["calendar_token_hash"],
            unique=True,
        )


def downgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_calendar_token_hash"))
        batch_op.drop_column("calendar_include_fertile")
        batch_op.drop_column("calendar_state")
        batch_op.drop_column("calendar_timezone")
        batch_op.drop_column("calendar_mark_estimate")
        batch_op.drop_column("calendar_fertile_label")
        batch_op.drop_column("calendar_label")
        batch_op.drop_column("calendar_token_hash")

    with op.batch_alter_table("planned_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_planned_events_user_id"))
    op.drop_table("planned_events")
