"""Add faqs_por_nivel (common FAQ block per level) to simulacro_departamentos.

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "simulacro_departamentos",
        sa.Column(
            "faqs_por_nivel",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("simulacro_departamentos", "faqs_por_nivel")
