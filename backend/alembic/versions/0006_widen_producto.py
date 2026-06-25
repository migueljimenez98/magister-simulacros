"""Widen simulacro_scenarios.producto 120 -> 500 (AI-generated values overflow).

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "simulacro_scenarios", "producto",
        existing_type=sa.String(length=120), type_=sa.String(length=500), existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "simulacro_scenarios", "producto",
        existing_type=sa.String(length=500), type_=sa.String(length=120), existing_nullable=True,
    )
