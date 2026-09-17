from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://news:news@localhost:5432/economic_data")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)


class Base(DeclarativeBase):
    pass


class EconomicEvent(Base):
    __tablename__ = "economic_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), default="forexfactory")
    source_event_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    event: Mapped[str] = mapped_column(String(255), index=True)
    event_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), index=True)
    impact: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    actual: Mapped[str | None] = mapped_column(Text, nullable=True)
    forecast: Mapped[str | None] = mapped_column(Text, nullable=True)
    previous: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


def init_db() -> None:
    Base.metadata.create_all(engine)


def upsert_events(events: list[dict[str, Any]]) -> int:
    inserted_or_updated = 0
    with Session(engine) as session:
        for data in events:
            key = data["source_event_key"]
            existing = session.scalar(select(EconomicEvent).where(EconomicEvent.source_event_key == key))
            if existing:
                for field in (
                    "event", "event_type", "currency", "impact", "timestamp_utc",
                    "actual", "forecast", "previous", "detail_url", "source_url"
                ):
                    setattr(existing, field, data.get(field))
            else:
                session.add(EconomicEvent(**data))
            inserted_or_updated += 1
        session.commit()
    return inserted_or_updated
