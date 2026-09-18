from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import settings
from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    profile: Mapped[LearnerProfile | None] = relationship(back_populates="user")


class LearnerProfile(Base):
    __tablename__ = "learner_profiles"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    academic_profile: Mapped[dict] = mapped_column(JSONB, default=dict)
    goals: Mapped[dict] = mapped_column(JSONB, default=dict)
    time_constraints: Mapped[dict] = mapped_column(JSONB, default=dict)
    learning_prefs: Mapped[dict] = mapped_column(JSONB, default=dict)
    behavioral_prefs: Mapped[dict] = mapped_column(JSONB, default=dict)

    user: Mapped[User] = relationship(back_populates="profile")


class Concept(Base):
    __tablename__ = "concepts"

    id: Mapped[int] = mapped_column(primary_key=True)
    subject: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(255))
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("concepts.id", ondelete="SET NULL")
    )
    prerequisites: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list)
    exam_weightage: Mapped[float] = mapped_column(Float, default=0.0)
    # Concept trees are seeded per user from subject templates; NULL = global concept.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )


class LearnerConceptState(Base):
    __tablename__ = "learner_concept_state"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    concept_id: Mapped[int] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE"), primary_key=True
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    mastery: Mapped[float] = mapped_column(Float, default=0.0)
    last_reviewed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retention_score: Mapped[float] = mapped_column(Float, default=2.5)
    misconceptions: Mapped[list] = mapped_column(JSONB, default=list)
    notes: Mapped[str | None] = mapped_column(Text)


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mode: Mapped[str] = mapped_column(String(32), default="teach")


class LessonBlock(Base):
    __tablename__ = "lesson_blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    concept_id: Mapped[int | None] = mapped_column(
        ForeignKey("concepts.id", ondelete="SET NULL")
    )
    type: Mapped[str] = mapped_column(String(40))  # intuition|analogy|theory|example|counter_example|question|summary
    content: Mapped[str] = mapped_column(Text)
    parent_block_id: Mapped[int | None] = mapped_column(
        ForeignKey("lesson_blocks.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Branch(Base):
    __tablename__ = "branches"

    id: Mapped[int] = mapped_column(primary_key=True)
    # NULL = free-form "new chat" under a concept rather than a lesson block
    parent_block_id: Mapped[int | None] = mapped_column(
        ForeignKey("lesson_blocks.id", ondelete="CASCADE"), index=True
    )
    concept_id: Mapped[int | None] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE"), index=True
    )
    question: Mapped[str] = mapped_column(Text)
    response: Mapped[str | None] = mapped_column(Text)
    # LangGraph checkpoint thread id — re-entering the branch resumes its own state.
    thread_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(512))
    source_type: Mapped[str] = mapped_column(String(20))  # pdf|pptx|image
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(settings.embedding_dim))


class Diagram(Base):
    __tablename__ = "diagrams"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE")
    )
    # concept this visual was created for — lets the UI list a concept's visuals
    concept_id: Mapped[int | None] = mapped_column(
        ForeignKey("concepts.id", ondelete="SET NULL"), index=True
    )
    image_url: Mapped[str] = mapped_column(String(1024))
    source: Mapped[str] = mapped_column(String(20), default="upload")  # upload|web|generated
    # [{label, bbox: [x, y, w, h], description}] from the one-time segmentation call.
    regions: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CropCache(Base):
    """Vision answers for arbitrary (non-pre-segmented) crops, shared across students.

    cache_key = sha256(f"{diagram_id}:{normalized bbox}") so repeated similar crops
    on a popular image never repay the vision cost.
    """

    __tablename__ = "crop_cache"

    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    diagram_id: Mapped[int] = mapped_column(
        ForeignKey("diagrams.id", ondelete="CASCADE"), index=True
    )
    bbox: Mapped[list] = mapped_column(JSONB)
    description: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TwinSnapshot(Base):
    __tablename__ = "twin_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    cognitive_profile: Mapped[dict] = mapped_column(JSONB, default=dict)
    knowledge_state: Mapped[dict] = mapped_column(JSONB, default=dict)
    misconception_ledger: Mapped[list] = mapped_column(JSONB, default=list)
    behavioral_profile: Mapped[dict] = mapped_column(JSONB, default=dict)
    snapshotted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (UniqueConstraint("user_id", "version", name="uq_twin_user_version"),)


class SimulationCache(Base):
    __tablename__ = "simulation_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    concept_id: Mapped[int] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE"), index=True
    )
    # Regenerate only for a meaningfully different framing; "default" fits most learners.
    variant_key: Mapped[str] = mapped_column(String(64), default="default")
    library: Mapped[str] = mapped_column(String(20))  # p5|matter|d3|three
    code: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("concept_id", "variant_key", name="uq_sim_concept_variant"),
    )


class SubjectTemplate(Base):
    __tablename__ = "subject_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    subject: Mapped[str] = mapped_column(String(120), unique=True)
    starter_concepts: Mapped[list] = mapped_column(JSONB, default=list)
    onboarding_questions: Mapped[list] = mapped_column(JSONB, default=list)
