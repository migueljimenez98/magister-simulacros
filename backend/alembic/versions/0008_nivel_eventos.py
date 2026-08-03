"""Historial de cambios de nivel de los agentes (simulacro_nivel_eventos).

Revision ID: 0008
Revises: 0007
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "simulacro_nivel_eventos",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "comercial_id",
            sa.String(length=64),
            sa.ForeignKey("simulacro_comerciales.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("agente_nombre", sa.String(length=200), nullable=False),
        sa.Column("department_id", sa.String(length=64), nullable=True),
        sa.Column("departamento", sa.String(length=120), nullable=True),
        sa.Column("from_nivel", sa.String(length=32), nullable=True),
        sa.Column("to_nivel", sa.String(length=32), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False, server_default="promote"),
        sa.Column("origen", sa.String(length=16), nullable=False, server_default="auto"),
        sa.Column("rule_id", sa.String(length=64), nullable=True),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("llamadas_en_nivel", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("llamadas_totales", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_percent_en_nivel", sa.Numeric(5, 2), nullable=True),
        sa.Column("actor", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_nivel_evento_agente_created",
        "simulacro_nivel_eventos",
        ["agente_nombre", "created_at"],
    )
    op.create_index(
        "ix_simulacro_nivel_eventos_agente_nombre",
        "simulacro_nivel_eventos",
        ["agente_nombre"],
    )


def downgrade() -> None:
    op.drop_index("ix_simulacro_nivel_eventos_agente_nombre", table_name="simulacro_nivel_eventos")
    op.drop_index("ix_nivel_evento_agente_created", table_name="simulacro_nivel_eventos")
    op.drop_table("simulacro_nivel_eventos")
