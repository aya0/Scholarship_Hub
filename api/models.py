from sqlalchemy import (
    Column, String, Float, Boolean, Text, Date,
    DateTime, Integer, ForeignKey, Enum, JSON
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum

Base = declarative_base()


def gen_uuid():
    return str(uuid.uuid4())


# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────

class ScholarshipType(str, enum.Enum):
    STUDY      = "study"
    WORK       = "work"
    VOLUNTEER  = "volunteer"
    TRAINING   = "training"
    RESEARCH   = "research"

class ScholarshipStatus(str, enum.Enum):
    OPEN   = "open"
    CLOSED = "closed"
    SOON   = "coming_soon"

class ScrapeStatus(str, enum.Enum):
    PENDING  = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"

class ApplicationStatus(str, enum.Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    SUBMITTED   = "submitted"
    ACCEPTED    = "accepted"
    REJECTED    = "rejected"

class NotifChannel(str, enum.Enum):
    EMAIL = "email"
    PUSH  = "push"


# ─────────────────────────────────────────────
# Core: Scholarship (curated, live)
# ─────────────────────────────────────────────

class Scholarship(Base):
    __tablename__ = "scholarships"

    id               = Column(UUID, primary_key=True, default=gen_uuid)
    title            = Column(String(500), nullable=False)
    slug             = Column(String(500), unique=True, nullable=False)
    type             = Column(Enum(ScholarshipType), nullable=False)
    country          = Column(String(100))
    funder           = Column(String(300))
    description      = Column(Text)
    eligibility      = Column(Text)
    application_steps= Column(Text)
    required_docs    = Column(JSON)          # ["CV", "Transcript", ...]
    open_date        = Column(Date)
    close_date       = Column(Date)
    degree_levels    = Column(JSON)          # ["Bachelor", "Master", ...]
    fields           = Column(JSON)          # ["Engineering", "Medicine", ...]
    language_req     = Column(String(100))
    min_gpa          = Column(Float)
    acceptance_rate  = Column(Float)
    funding_amount   = Column(String(200))
    application_url  = Column(String(1000))
    source_url       = Column(String(1000))
    status           = Column(Enum(ScholarshipStatus), default=ScholarshipStatus.OPEN)
    is_active        = Column(Boolean, default=True)
    created_at       = Column(DateTime, server_default=func.now())
    updated_at       = Column(DateTime, onupdate=func.now())
    created_by       = Column(UUID, ForeignKey("users.id"))

    # relationships
    applications  = relationship("Application",  back_populates="scholarship")
    favorites     = relationship("Favorite",     back_populates="scholarship")
    ai_matches    = relationship("AIMatch",      back_populates="scholarship")
    notifications = relationship("Notification", back_populates="scholarship")
    stories       = relationship("SuccessStory", back_populates="scholarship")
    scrape_record = relationship("ScrapeResult", back_populates="scholarship", uselist=False)


# ─────────────────────────────────────────────
# Scraper: Raw scraped candidates (unpublished)
# ─────────────────────────────────────────────

class ScrapeResult(Base):
    """
    Every item the scraper finds lands here first.
    Admin reviews and either approves (→ creates Scholarship)
    or rejects / marks as duplicate.
    Nothing in this table is ever shown to end users.
    """
    __tablename__ = "scrape_results"

    id              = Column(UUID, primary_key=True, default=gen_uuid)
    source_name     = Column(String(200), nullable=False)   # "daad", "chevening", ...
    source_url      = Column(String(1000), nullable=False)
    raw_html        = Column(Text)
    extracted        = Column(JSON)    # parsed fields before normalization
    normalized       = Column(JSON)    # AI-normalized fields ready for review
    status          = Column(Enum(ScrapeStatus), default=ScrapeStatus.PENDING)
    duplicate_of    = Column(UUID, ForeignKey("scholarships.id"), nullable=True)
    admin_notes     = Column(Text)
    reviewed_by     = Column(UUID, ForeignKey("users.id"), nullable=True)
    reviewed_at     = Column(DateTime, nullable=True)
    scholarship_id  = Column(UUID, ForeignKey("scholarships.id"), nullable=True)
    scraped_at      = Column(DateTime, server_default=func.now())
    content_hash    = Column(String(64), unique=True)   # SHA256 of normalized title+url

    scholarship = relationship("Scholarship", back_populates="scrape_record",
                               foreign_keys=[scholarship_id])


# ─────────────────────────────────────────────
# Scraper: Source registry
# ─────────────────────────────────────────────

class ScrapeSource(Base):
    """Registry of all monitored websites."""
    __tablename__ = "scrape_sources"

    id           = Column(UUID, primary_key=True, default=gen_uuid)
    name         = Column(String(200), unique=True, nullable=False)
    base_url     = Column(String(1000), nullable=False)
    scraper_key  = Column(String(100), nullable=False)  # maps to scraper class
    is_active    = Column(Boolean, default=True)
    interval_hrs = Column(Integer, default=24)
    last_scraped = Column(DateTime, nullable=True)
    total_found  = Column(Integer, default=0)
    total_approved = Column(Integer, default=0)
    notes        = Column(Text)


# ─────────────────────────────────────────────
# Users & profiles
# ─────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id            = Column(UUID, primary_key=True, default=gen_uuid)
    full_name     = Column(String(300))
    email         = Column(String(300), unique=True, nullable=False)
    password_hash = Column(String(500))
    role          = Column(String(50), default="user")   # user / admin / moderator
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime, server_default=func.now())

    profile       = relationship("UserProfile",  back_populates="user", uselist=False)
    applications  = relationship("Application",  back_populates="user")
    favorites     = relationship("Favorite",     back_populates="user")
    ai_matches    = relationship("AIMatch",      back_populates="user")
    notifications = relationship("Notification", back_populates="user")
    documents     = relationship("Document",     back_populates="user")
    stories       = relationship("SuccessStory", back_populates="user")


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id               = Column(UUID, primary_key=True, default=gen_uuid)
    user_id          = Column(UUID, ForeignKey("users.id"), unique=True, nullable=False)
    gpa              = Column(Float)
    degree_level     = Column(String(100))
    field_of_study   = Column(String(200))
    language_cert    = Column(String(100))
    language_score   = Column(Float)
    experience_years = Column(Integer, default=0)
    nationality_doc  = Column(String(200))
    financial_status = Column(String(100))
    target_countries = Column(JSON)   # ["Germany", "Turkey", ...]
    target_types     = Column(JSON)   # ["study", "volunteer"]
    cv_url           = Column(String(1000))
    updated_at       = Column(DateTime, onupdate=func.now())

    user = relationship("User", back_populates="profile")


# ─────────────────────────────────────────────
# User activity tables
# ─────────────────────────────────────────────

class Favorite(Base):
    __tablename__ = "favorites"
    id             = Column(UUID, primary_key=True, default=gen_uuid)
    user_id        = Column(UUID, ForeignKey("users.id"), nullable=False)
    scholarship_id = Column(UUID, ForeignKey("scholarships.id"), nullable=False)
    saved_at       = Column(DateTime, server_default=func.now())

    user        = relationship("User",        back_populates="favorites")
    scholarship = relationship("Scholarship", back_populates="favorites")


class Application(Base):
    __tablename__ = "applications"
    id             = Column(UUID, primary_key=True, default=gen_uuid)
    user_id        = Column(UUID, ForeignKey("users.id"), nullable=False)
    scholarship_id = Column(UUID, ForeignKey("scholarships.id"), nullable=False)
    status         = Column(Enum(ApplicationStatus), default=ApplicationStatus.NOT_STARTED)
    submitted_at   = Column(Date, nullable=True)
    notes          = Column(Text)
    updated_at     = Column(DateTime, onupdate=func.now())

    user        = relationship("User",        back_populates="applications")
    scholarship = relationship("Scholarship", back_populates="applications")


class AIMatch(Base):
    __tablename__ = "ai_matches"
    id             = Column(UUID, primary_key=True, default=gen_uuid)
    user_id        = Column(UUID, ForeignKey("users.id"), nullable=False)
    scholarship_id = Column(UUID, ForeignKey("scholarships.id"), nullable=False)
    match_score    = Column(Float)
    gap_analysis   = Column(Text)
    suggestions    = Column(Text)
    generated_at   = Column(DateTime, server_default=func.now())

    user        = relationship("User",        back_populates="ai_matches")
    scholarship = relationship("Scholarship", back_populates="ai_matches")


class Notification(Base):
    __tablename__ = "notifications"
    id             = Column(UUID, primary_key=True, default=gen_uuid)
    user_id        = Column(UUID, ForeignKey("users.id"), nullable=False)
    scholarship_id = Column(UUID, ForeignKey("scholarships.id"), nullable=True)
    type           = Column(String(100))   # "deadline_reminder", "new_match", ...
    channel        = Column(Enum(NotifChannel))
    message        = Column(Text)
    sent           = Column(Boolean, default=False)
    scheduled_at   = Column(DateTime)
    sent_at        = Column(DateTime, nullable=True)

    user        = relationship("User",        back_populates="notifications")
    scholarship = relationship("Scholarship", back_populates="notifications")


class Document(Base):
    __tablename__ = "documents"
    id          = Column(UUID, primary_key=True, default=gen_uuid)
    user_id     = Column(UUID, ForeignKey("users.id"), nullable=False)
    doc_type    = Column(String(100))   # "cv", "transcript", "recommendation"
    file_url    = Column(String(1000))
    uploaded_at = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="documents")


class SuccessStory(Base):
    __tablename__ = "success_stories"
    id             = Column(UUID, primary_key=True, default=gen_uuid)
    user_id        = Column(UUID, ForeignKey("users.id"), nullable=False)
    scholarship_id = Column(UUID, ForeignKey("scholarships.id"), nullable=False)
    story_text     = Column(Text)
    verified       = Column(Boolean, default=False)
    published_at   = Column(DateTime, nullable=True)

    user        = relationship("User",        back_populates="stories")
    scholarship = relationship("Scholarship", back_populates="stories")
