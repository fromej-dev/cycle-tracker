"""Per-day symptom log

Revision ID: e6a3c7d94f21
Revises: d5f9b2c83e17
Create Date: 2026-10-28 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "e6a3c7d94f21"
down_revision = "d5f9b2c83e17"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "symptom_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("symptoms", sa.Text(), nullable=False),
        sa.Column("custom", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "date", name="uq_symptom_logs_user_date"),
    )
    with op.batch_alter_table("symptom_logs", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_symptom_logs_user_id"), ["user_id"], unique=False
        )


def downgrade():
    with op.batch_alter_table("symptom_logs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_symptom_logs_user_id"))
    op.drop_table("symptom_logs")
