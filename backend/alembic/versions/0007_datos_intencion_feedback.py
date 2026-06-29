"""Personalidad: datos_agente + intencion. Analisis: admin_feedback.

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("simulacro_scenarios", sa.Column("datos_agente", sa.Text(), nullable=False, server_default=""))
    op.add_column("simulacro_scenarios", sa.Column("intencion", sa.Text(), nullable=False, server_default=""))
    op.add_column("quality_analyses", sa.Column("admin_feedback", sa.String(length=8), nullable=True))


def downgrade() -> None:
    op.drop_column("quality_analyses", "admin_feedback")
    op.drop_column("simulacro_scenarios", "intencion")
    op.drop_column("simulacro_scenarios", "datos_agente")
