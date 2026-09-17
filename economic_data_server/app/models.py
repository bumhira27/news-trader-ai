from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.sql import func
from .db import Base

class EconomicEvent(Base):
    __tablename__ = "economic_events"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    source = Column(String(50), nullable=False, default="forexfactory", index=True)
    source_event_key = Column(String(255), unique=True, nullable=False, index=True)
    event = Column(String(255), nullable=False, index=True)
    event_type = Column(String(100), nullable=True, index=True)
    currency = Column(String(10), nullable=False, index=True)
    impact = Column(String(20), nullable=False, index=True)
    timestamp_utc = Column(DateTime(timezone=True), nullable=False, index=True)
    actual = Column(Text, nullable=True)
    forecast = Column(Text, nullable=True)
    previous = Column(Text, nullable=True)
    detail_url = Column(Text, nullable=True)
    source_url = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_economic_events_currency_timestamp", "currency", "timestamp_utc"),
        Index("ix_economic_events_impact_timestamp", "impact", "timestamp_utc"),
    )

class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    started_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    finished_at = Column(DateTime(timezone=True), nullable=True)
    source = Column(String(50), nullable=False, default="forexfactory")
    requested_start = Column(String(50), nullable=True)
    requested_end = Column(String(50), nullable=True)
    records_found = Column(Integer, default=0)
    records_inserted = Column(Integer, default=0)
    records_updated = Column(Integer, default=0)
    records_rejected = Column(Integer, default=0)
    status = Column(String(20), nullable=False, default="running")
    error_message = Column(Text, nullable=True)

class EventRevision(Base):
    __tablename__ = "event_revisions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey("economic_events.id", ondelete="CASCADE"), nullable=False, index=True)
    field_name = Column(String(50), nullable=False)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    changed_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
