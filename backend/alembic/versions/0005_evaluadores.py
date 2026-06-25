"""Independent evaluadores catalog + departamento.evaluador_id.

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "simulacro_evaluadores",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("nombre", sa.String(length=160), nullable=False),
        sa.Column("auditor_prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("feedback_prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("report_prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("rules_table", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column(
        "simulacro_departamentos",
        sa.Column(
            "evaluador_id", sa.String(length=64),
            sa.ForeignKey("simulacro_evaluadores.id", ondelete="SET NULL"), nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("simulacro_departamentos", "evaluador_id")
    op.drop_table("simulacro_evaluadores")
