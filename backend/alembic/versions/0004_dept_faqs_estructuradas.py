"""Add structured `faqs` (pregunta/respuesta_esperada/nivel) to departamentos.

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "simulacro_departamentos",
        sa.Column("faqs", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("simulacro_departamentos", "faqs")
