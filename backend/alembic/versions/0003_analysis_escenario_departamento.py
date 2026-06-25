"""Add denormalized escenario + departamento to quality_analyses (results table).

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("quality_analyses", sa.Column("escenario", sa.String(length=200), nullable=True))
    op.add_column("quality_analyses", sa.Column("departamento", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("quality_analyses", "departamento")
    op.drop_column("quality_analyses", "escenario")
