"""SQLAlchemy ORM models for Wazi.

Tables:
    users     — hashed WhatsApp identities (no PII stored)
    sessions  — conversation sessions (one per user chat window)
    messages  — individual Q&A pairs with citations
    disputes  — citizen reports on inaccurate answers
    sources   — registry of ingested government documents
    chunks    — text chunks with pgvector embeddings for RAG retrieval
"""

import enum
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# --- Enums ------------------------------------------------------------------

class GovernmentArm(str, enum.Enum):
    """Which arm of county government a document covers."""
    EXECUTIVE = "executive"           # County Executive audit (service delivery, infrastructure)
    ASSEMBLY = "assembly"             # County Assembly audit (legislative operations, MCA spending)
    CONSOLIDATED = "consolidated"     # CoB consolidated BIRRs (all arms combined)
    REVENUE = "revenue"               # County Receiver of Revenue (own-source revenue)


class ReportType(str, enum.Enum):
    """The financial document type."""
    AUDIT_REPORT = "audit_report"         # OAG annual audit
    BIRR = "birr"                         # CoB Budget Implementation Review Report
    EXCHEQUER = "exchequer"               # CoB monthly exchequer releases
    CBROP = "cbrop"                       # County Budget Review and Outlook Paper (KIPPRA)
    PROGRAMME_BUDGET = "programme_budget"  # Approved Programme-Based Budget Estimates (KIPPRA)
    # Future: CFSP, ADP, CITIZENS_BUDGET, CIDP, PROCUREMENT


class IngestionStatus(str, enum.Enum):
    """Where a source document is in the ingestion pipeline."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class DisputeStatus(str, enum.Enum):
    """Lifecycle of a citizen dispute report."""
    PENDING_REVIEW = "pending_review"
    UNDER_REVIEW = "under_review"
    RESOLVED_VALID = "resolved_valid"       # Dispute was correct — answer had an issue
    RESOLVED_INVALID = "resolved_invalid"   # Dispute was incorrect — answer was accurate
    ESCALATED = "escalated"                 # Escalated to external authority (e.g., EACC)


class ValidationRegister(str, enum.Enum):
    """The language register a linguist judged an answer to be written in."""
    FORMAL_SWAHILI = "formal_swahili"
    SHENG = "sheng"
    ENGLISH = "english"
    MIXED = "mixed"


# --- Tables -----------------------------------------------------------------

class User(Base):
    """A citizen, identified only by their hashed WhatsApp ID.

    The raw wa_id is SHA-256 hashed with a secret salt on receipt and NEVER
    stored. This table contains no PII (no phone number, name, or location).
    """
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hashed_wa_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    sessions: Mapped[list["Session"]] = relationship(back_populates="user")

    def __repr__(self) -> str:
        return f"<User id={self.id}>"


class Session(Base):
    """A conversation session — one per citizen chat window.

    A new session starts when a citizen sends their first message after a
    period of inactivity (or when they explicitly say "anza upya" / start over).
    """
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User"] = relationship(back_populates="sessions")
    messages: Mapped[list["Message"]] = relationship(back_populates="session")

    def __repr__(self) -> str:
        return f"<Session id={self.id} user_id={self.user_id}>"


class Message(Base):
    """A single Q&A exchange: the citizen's question and Wazi's answer.

    Citation traces the answer back to a specific source document and page.
    """
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # "user" or "assistant"
    text: Mapped[str] = mapped_column(Text, nullable=False)
    citation: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # JSON snapshot of the chunks retrieval showed the model when it produced
    # this answer. Stored denormalized so the moderation/escalation loop keeps
    # an immutable record of "what the AI was shown" even after re-ingestion.
    retrieved_chunks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    session: Mapped["Session"] = relationship(back_populates="messages")
    disputes: Mapped[list["Dispute"]] = relationship(back_populates="message")

    def __repr__(self) -> str:
        return f"<Message id={self.id} role={self.role}>"


class Dispute(Base):
    """A citizen report that an answer may be inaccurate.

    SECURITY: This table stores the reporter's hashed user ID for anti-bot
    diversity checks, but does NOT store the original query text. The message
    content lives in the Messages table. There is no direct join path from
    this table to the identity of the citizen who asked the question being
    disputed — the dispute is a signal on the *answer*, not a dossier.
    """
    __tablename__ = "disputes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(
        ForeignKey("messages.id"), nullable=False, index=True
    )
    reported_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[DisputeStatus] = mapped_column(
        Enum(DisputeStatus), default=DisputeStatus.PENDING_REVIEW, nullable=False
    )
    reviewed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    message: Mapped["Message"] = relationship(back_populates="disputes")

    # Prevent duplicate disputes from the same user on the same answer.
    __table_args__ = (
        UniqueConstraint(
            "message_id", "reported_by_user_id",
            name="uq_dispute_one_per_user",
        ),
    )


class Source(Base):
    """A government document registered for ingestion into the corpus.

    The source registry is the single source of truth for what documents
    Wazi has ingested. The scheduler reads from this table to know what
    to scrape and when.
    """
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    publisher: Mapped[str] = mapped_column(String(128), nullable=False)  # "OAG", "CoB"
    government_arm: Mapped[GovernmentArm] = mapped_column(
        Enum(GovernmentArm), nullable=False
    )
    county: Mapped[str] = mapped_column(String(64), nullable=False, default="nakuru")
    report_type: Mapped[ReportType] = mapped_column(Enum(ReportType), nullable=False)
    fiscal_year: Mapped[str | None] = mapped_column(String(16), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ingestion_status: Mapped[IngestionStatus] = mapped_column(
        Enum(IngestionStatus), default=IngestionStatus.PENDING, nullable=False
    )
    ingestion_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default=None
    )  # SHA-256 of the downloaded PDF — detects silent server-side swaps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    chunks: Mapped[list["Chunk"]] = relationship(back_populates="source")

    def __repr__(self) -> str:
        return f"<Source id={self.id} title={self.title}>"


class Chunk(Base):
    """A text chunk with its pgvector embedding for semantic search.

    Metadata (government_arm, county) is denormalized from the Source so
    retrieval can filter without a JOIN — important for vector search speed.
    """
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id"), nullable=False, index=True
    )
    government_arm: Mapped[GovernmentArm] = mapped_column(
        Enum(GovernmentArm), nullable=False
    )
    county: Mapped[str] = mapped_column(String(64), nullable=False, default="nakuru")
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        Vector(384), nullable=False  # 384 = MiniLM embedding dimension
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    source: Mapped["Source"] = relationship(back_populates="chunks")

    # Composite index for filtered vector search:
    # "find chunks about X within Nakuru county executive reports"
    __table_args__ = (
        UniqueConstraint("source_id", "page_number", "chunk_index", name="uq_chunk_location"),
    )

    def __repr__(self) -> str:
        return f"<Chunk id={self.id} source_id={self.source_id} page={self.page_number}>"


class Validation(Base):
    """A linguist's quality rating of a generated answer.

    Feeds the answer-feedback loop (strategic plan §6.1): native speakers rate
    tone, grounding, and register so the system prompt can be improved. Points
    at the assistant Message being rated; the original question is derived from
    the preceding user message in the same session, so this table holds no
    identity link — it is a signal on the *answer*, not on the citizen.
    """
    __tablename__ = "validations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(
        ForeignKey("messages.id"), nullable=False, index=True
    )
    tone_score: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5
    grounded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    register: Mapped[ValidationRegister] = mapped_column(
        Enum(ValidationRegister), nullable=False
    )
    reviewer: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        return f"<Validation id={self.id} message_id={self.message_id} tone={self.tone_score}>"
