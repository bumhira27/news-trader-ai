from __future__ import annotations

from datetime import date, datetime, time, timezone

from fastapi import FastAPI, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import EconomicEvent, engine, init_db

app = FastAPI(title="News Trader Economic Data Server", version="0.1.0")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/events")
def events(
    start: date | None = None,
    end: date | None = None,
    currency: str | None = None,
    impact: str | None = None,
    event: str | None = None,
    limit: int = Query(default=500, ge=1, le=5000),
) -> list[dict]:
    stmt = select(EconomicEvent).order_by(EconomicEvent.timestamp_utc).limit(limit)
    if start:
        stmt = stmt.where(EconomicEvent.timestamp_utc >= datetime.combine(start, time.min, tzinfo=timezone.utc))
    if end:
        stmt = stmt.where(EconomicEvent.timestamp_utc < datetime.combine(end, time.min, tzinfo=timezone.utc))
    if currency:
        stmt = stmt.where(EconomicEvent.currency == currency.upper())
    if impact:
        stmt = stmt.where(EconomicEvent.impact == impact)
    if event:
        stmt = stmt.where(EconomicEvent.event.ilike(f"%{event}%"))

    with Session(engine) as session:
        rows = session.scalars(stmt).all()
        return [
            {
                "id": row.id,
                "source": row.source,
                "event": row.event,
                "event_type": row.event_type,
                "currency": row.currency,
                "impact": row.impact,
                "timestamp_utc": row.timestamp_utc,
                "actual": row.actual,
                "forecast": row.forecast,
                "previous": row.previous,
                "detail_url": row.detail_url,
            }
            for row in rows
        ]


@app.get("/api/v1/calendar/{year}/{month}")
def calendar(year: int, month: int) -> list[dict]:
    start = date(year, month, 1)
    end = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    return events(start=start, end=end, limit=5000)
