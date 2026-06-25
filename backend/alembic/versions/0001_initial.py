"""initial schema — magister-simulacros

Revision ID: 0001
Revises:
Create Date: 2026-06-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255)),
        sa.Column("role", sa.String(32), nullable=False, server_default="admin"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "quality_projects",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("analysis_mode", sa.String(32), server_default="statistical"),
        sa.Column("rules_table", JSONB, nullable=False, server_default="[]"),
        sa.Column("kb_collection_id", sa.String(64), nullable=False, server_default="default"),
        sa.Column("config", JSONB, nullable=False, server_default="{}"),
        sa.Column("prompts", JSONB, nullable=False, server_default="{}"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "quality_analyses",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("quality_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("numero", sa.String(64), nullable=False, server_default="simulacro"),
        sa.Column("agente_nombre", sa.String(200), nullable=False),
        sa.Column("call_date", sa.DateTime(timezone=True)),
        sa.Column("instruction", sa.Text),
        sa.Column("scores", JSONB, nullable=False, server_default="{}"),
        sa.Column("scores_by_dimension", JSONB, nullable=False, server_default="{}"),
        sa.Column("total_score", sa.Numeric(6, 2)),
        sa.Column("ideal_score", sa.Numeric(6, 2)),
        sa.Column("percent_quality", sa.Numeric(5, 2)),
        sa.Column("feedback_message", sa.Text),
        sa.Column("feedback_by_vertical", JSONB, nullable=False, server_default="{}"),
        sa.Column("feedback_selected_tier", sa.String(32)),
        sa.Column("coach_validation_notes", JSONB, nullable=False, server_default="[]"),
        sa.Column("detailed_report", sa.Text),
        sa.Column("crm_snapshot", JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_qa_project_created", "quality_analyses", ["project_id", "created_at"])
    op.create_index("ix_qa_agente_created", "quality_analyses", ["agente_nombre", "created_at"])
    op.create_index("ix_quality_analyses_numero", "quality_analyses", ["numero"])

    op.create_table(
        "kb_documents",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("collection_id", sa.String(64), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("source", sa.String(64), server_default="upload"),
        sa.Column("file_path", sa.String(1000)),
        sa.Column("file_size", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("mime_type", sa.String(100), server_default="text/markdown"),
        sa.Column("extra_metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_kb_documents_collection_id", "kb_documents", ["collection_id"])

    op.create_table(
        "kb_chunks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("document_id", sa.String(64), sa.ForeignKey("kb_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("collection_id", sa.String(64), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("embedding", Vector(1536)),
        sa.Column("extra_metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_kb_chunks_document_id", "kb_chunks", ["document_id"])
    op.create_index("ix_kb_chunks_collection_id", "kb_chunks", ["collection_id"])
    op.create_index("ix_kbchunk_doc_idx", "kb_chunks", ["document_id", "chunk_index"])

    op.create_table(
        "simulacro_departamentos",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("nombre", sa.String(120), nullable=False, unique=True),
        sa.Column("niveles", JSONB, nullable=False, server_default='["facil","medio","dificil"]'),
        sa.Column("reglas", JSONB, nullable=False, server_default="[]"),
        sa.Column("auto_evaluar", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("quality_projects.id", ondelete="SET NULL")),
        sa.Column("activo", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "simulacro_scenarios",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("quality_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("department_id", sa.String(64), sa.ForeignKey("simulacro_departamentos.id", ondelete="SET NULL")),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("dificultad", sa.String(32), nullable=False, server_default="medio"),
        sa.Column("producto", sa.String(120)),
        sa.Column("persona", sa.Text, nullable=False, server_default=""),
        sa.Column("objeciones", sa.Text, nullable=False, server_default=""),
        sa.Column("faqs", sa.Text, nullable=False, server_default=""),
        sa.Column("guion", sa.Text, nullable=False, server_default=""),
        sa.Column("retell_agent_id", sa.String(120)),
        sa.Column("activo", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_sce_project_activo", "simulacro_scenarios", ["project_id", "activo"])

    op.create_table(
        "simulacro_comerciales",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("extension", sa.String(64)),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("activo", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("department_id", sa.String(64), sa.ForeignKey("simulacro_departamentos.id", ondelete="SET NULL")),
        sa.Column("nivel", sa.String(32)),
        sa.Column("default_scenario_id", sa.String(64), sa.ForeignKey("simulacro_scenarios.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("simulacro_comerciales")
    op.drop_table("simulacro_scenarios")
    op.drop_table("simulacro_departamentos")
    op.drop_table("kb_chunks")
    op.drop_table("kb_documents")
    op.drop_table("quality_analyses")
    op.drop_table("quality_projects")
    op.drop_table("users")
