"""Database schema — magister-simulacros (lightweight).

Only what the simulacros product needs:
  - users               : login + role
  - quality_projects    : the rubric + evaluator prompts + KB collection
  - quality_analyses    : one scored simulacro (transcript in crm_snapshot)
  - kb_documents/chunks : guión/templates for the coach grounding (pgvector)
  - simulacro_departamentos / scenarios / comerciales : config + levels
"""
from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(6)}"


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: _id("usr"))
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="admin")  # admin | viewer
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class QualityProject(Base):
    """The evaluador config: rubric (`rules_table`) + prompts + KB collection."""
    __tablename__ = "quality_projects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: _id("proj"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    analysis_mode: Mapped[str] = mapped_column(String(32), default="statistical")
    rules_table: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    kb_collection_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    prompts: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class QualityAnalysis(Base):
    """One scored simulacro. The transcript + scenario live in crm_snapshot."""
    __tablename__ = "quality_analyses"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: _id("qa"))
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("quality_projects.id", ondelete="CASCADE"), nullable=False
    )
    numero: Mapped[str] = mapped_column(String(64), nullable=False, default="simulacro", index=True)
    agente_nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    # Denormalized for the results table (like agente_nombre): which guión was
    # used and which departamento it belongs to. Written by the persist node.
    escenario: Mapped[str | None] = mapped_column(String(200))
    departamento: Mapped[str | None] = mapped_column(String(120))
    call_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    instruction: Mapped[str | None] = mapped_column(Text)

    scores: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    scores_by_dimension: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    total_score: Mapped[float | None] = mapped_column(Numeric(6, 2))
    ideal_score: Mapped[float | None] = mapped_column(Numeric(6, 2))
    percent_quality: Mapped[float | None] = mapped_column(Numeric(5, 2))
    feedback_message: Mapped[str | None] = mapped_column(Text)
    feedback_by_vertical: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    feedback_selected_tier: Mapped[str | None] = mapped_column(String(32))
    coach_validation_notes: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    detailed_report: Mapped[str | None] = mapped_column(Text)
    crm_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_qa_project_created", "project_id", "created_at"),
        Index("ix_qa_agente_created", "agente_nombre", "created_at"),
    )


class KbDocument(Base):
    __tablename__ = "kb_documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: _id("kbd"))
    collection_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    source: Mapped[str] = mapped_column(String(64), default="upload")
    file_path: Mapped[str | None] = mapped_column(String(1000))
    file_size: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), default="text/markdown")
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class KbChunk(Base):
    __tablename__ = "kb_chunks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: _id("chk"))
    document_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("kb_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    collection_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536))
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_kbchunk_doc_idx", "document_id", "chunk_index"),
    )


# ── Simulacros: departamentos / escenarios / comerciales ────────────────────


class SimulacroDepartamento(Base):
    __tablename__ = "simulacro_departamentos"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: _id("dep"))
    nombre: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    niveles: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=lambda: ["facil", "medio", "dificil"],
        server_default=text("'[\"facil\",\"medio\",\"dificil\"]'::jsonb"),
    )
    # Bloque común de FAQs por nivel: {"facil": "...", "medio": "...", ...}.
    # Se inyecta en la llamada según el nivel del comercial, además de las FAQs
    # propias del guion.
    faqs_por_nivel: Mapped[dict[str, str]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    reglas: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    auto_evaluar: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    project_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("quality_projects.id", ondelete="SET NULL")
    )
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SimulacroScenario(Base):
    __tablename__ = "simulacro_scenarios"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: _id("sce"))
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("quality_projects.id", ondelete="CASCADE"), nullable=False
    )
    department_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("simulacro_departamentos.id", ondelete="SET NULL")
    )
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    dificultad: Mapped[str] = mapped_column(String(32), nullable=False, default="medio")
    producto: Mapped[str | None] = mapped_column(String(120))
    persona: Mapped[str] = mapped_column(Text, nullable=False, default="")
    objeciones: Mapped[str] = mapped_column(Text, nullable=False, default="")
    faqs: Mapped[str] = mapped_column(Text, nullable=False, default="")
    guion: Mapped[str] = mapped_column(Text, nullable=False, default="")
    retell_agent_id: Mapped[str | None] = mapped_column(String(120))
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_sce_project_activo", "project_id", "activo"),
    )


class SimulacroComercial(Base):
    __tablename__ = "simulacro_comerciales"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: _id("scm"))
    extension: Mapped[str | None] = mapped_column(String(64))
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    department_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("simulacro_departamentos.id", ondelete="SET NULL")
    )
    nivel: Mapped[str | None] = mapped_column(String(32))
    default_scenario_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("simulacro_scenarios.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
