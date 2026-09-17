import calendar
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from .db import get_db, init_db
from .models import EconomicEvent, IngestionRun
from .schemas import (
    EconomicEventResponse,
    IngestionRunResponse,
    HealthResponse,
    ValidationReport
)

from contextlib import asynccontextmanager
from sqlalchemy import select

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(
    title="Economic Data Server",
    description="Dedicated economic-calendar context API providing factual macroeconomic release facts for News Trader AI.",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/health", response_model=HealthResponse, tags=["Health"])
def health_check(db: Session = Depends(get_db)):
    """Health check endpoint confirming service and database status."""
    try:
        db.execute(select(EconomicEvent.id).limit(1))
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {e}"

    return HealthResponse(
        status="ok",
        service="economic_data_server",
        database=db_status,
        version="1.0.0"
    )

@app.get("/api/v1/events", response_model=List[EconomicEventResponse], tags=["Events"])
def get_events(
    start: Optional[str] = Query(None, description="Start date/time (ISO 8601 or YYYY-MM-DD)"),
    end: Optional[str] = Query(None, description="End date/time (ISO 8601 or YYYY-MM-DD)"),
    currency: Optional[str] = Query(None, description="Currency filter (e.g. USD, EUR)"),
    impact: Optional[str] = Query(None, description="Impact filter (e.g. High, Medium, Low)"),
    event: Optional[str] = Query(None, description="Event name substring filter"),
    event_type: Optional[str] = Query(None, description="Event category/type filter"),
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Retrieve normalized economic calendar events with flexible filtering."""
    query = db.query(EconomicEvent)

    if start:
        try:
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        except ValueError:
            start_dt = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        query = query.filter(EconomicEvent.timestamp_utc >= start_dt)

    if end:
        try:
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
        except ValueError:
            end_dt = datetime.strptime(end, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
        query = query.filter(EconomicEvent.timestamp_utc <= end_dt)

    if currency:
        query = query.filter(EconomicEvent.currency == currency.upper())

    if impact:
        query = query.filter(EconomicEvent.impact.ilike(f"%{impact}%"))

    if event:
        query = query.filter(EconomicEvent.event.ilike(f"%{event}%"))

    if event_type:
        query = query.filter(EconomicEvent.event_type.ilike(f"%{event_type}%"))

    query = query.order_by(EconomicEvent.timestamp_utc.asc())
    return query.offset(offset).limit(limit).all()

@app.get("/api/v1/calendar/{year}/{month}", response_model=List[EconomicEventResponse], tags=["Calendar"])
def get_monthly_calendar(
    year: int,
    month: int,
    currency: Optional[str] = Query(None, description="Currency filter"),
    db: Session = Depends(get_db)
):
    """Retrieve all economic events for a specific calendar month."""
    if not (1 <= month <= 12):
        raise HTTPException(status_code=400, detail="Month must be between 1 and 12")

    _, last_day = calendar.monthrange(year, month)
    start_dt = datetime(year, month, 1, 0, 0, 0, tzinfo=timezone.utc)
    end_dt = datetime(year, month, last_day, 23, 59, 59, 999999, tzinfo=timezone.utc)

    query = db.query(EconomicEvent).filter(
        EconomicEvent.timestamp_utc >= start_dt,
        EconomicEvent.timestamp_utc <= end_dt
    )

    if currency:
        query = query.filter(EconomicEvent.currency == currency.upper())

    return query.order_by(EconomicEvent.timestamp_utc.asc()).all()

@app.get("/api/v1/events/{event_id}", response_model=EconomicEventResponse, tags=["Events"])
def get_single_event(event_id: int, db: Session = Depends(get_db)):
    """Retrieve a single economic event by ID."""
    ev = db.query(EconomicEvent).filter(EconomicEvent.id == event_id).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")
    return ev

@app.get("/api/v1/news-events", response_model=List[EconomicEventResponse], tags=["News Trader Context"])
def get_news_relevant_events(
    currency: str = Query("USD", description="Currency to filter"),
    high_impact_only: bool = Query(True, description="Filter strictly High impact"),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """
    Supplies factual high-relevance economic context for News Trader AI decision engines.
    Does not produce trading decisions.
    """
    query = db.query(EconomicEvent).filter(EconomicEvent.currency == currency.upper())

    if high_impact_only:
        query = query.filter(EconomicEvent.impact == "High")
    else:
        query = query.filter(EconomicEvent.impact.in_(["High", "Medium"]))

    if start:
        try:
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        except ValueError:
            start_dt = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        query = query.filter(EconomicEvent.timestamp_utc >= start_dt)

    if end:
        try:
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
        except ValueError:
            end_dt = datetime.strptime(end, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
        query = query.filter(EconomicEvent.timestamp_utc <= end_dt)

    return query.order_by(EconomicEvent.timestamp_utc.asc()).limit(limit).all()

@app.get("/api/v1/ingest/runs", response_model=List[IngestionRunResponse], tags=["Ingestion"])
def get_ingestion_runs(limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    """List recent ingestion operations and execution metrics."""
    return db.query(IngestionRun).order_by(desc(IngestionRun.id)).limit(limit).all()

@app.get("/api/v1/validation-report", response_model=ValidationReport, tags=["Data Quality"])
def get_validation_report(
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Generate data quality audit report verifying total, unique, duplicate,
    and missing values across records (as specified in Section 33).
    """
    query = db.query(EconomicEvent)
    if year and month:
        _, last_day = calendar.monthrange(year, month)
        start_dt = datetime(year, month, 1, 0, 0, 0, tzinfo=timezone.utc)
        end_dt = datetime(year, month, last_day, 23, 59, 59, 999999, tzinfo=timezone.utc)
        query = query.filter(
            EconomicEvent.timestamp_utc >= start_dt,
            EconomicEvent.timestamp_utc <= end_dt
        )

    all_events = query.all()
    total = len(all_events)

    keys = set()
    dup_count = 0
    missing_ts = 0
    missing_curr = 0
    missing_name = 0
    missing_act = 0
    missing_fcst = 0
    missing_prev = 0

    curr_counts = {}
    impact_counts = {}

    for e in all_events:
        if e.source_event_key in keys:
            dup_count += 1
        keys.add(e.source_event_key)

        if not e.timestamp_utc: missing_ts += 1
        if not e.currency: missing_curr += 1
        if not e.event: missing_name += 1
        if e.actual is None: missing_act += 1
        if e.forecast is None: missing_fcst += 1
        if e.previous is None: missing_prev += 1

        curr_counts[e.currency] = curr_counts.get(e.currency, 0) + 1
        impact_counts[e.impact] = impact_counts.get(e.impact, 0) + 1

    return ValidationReport(
        total_records=total,
        unique_records=len(keys),
        duplicate_records=dup_count,
        missing_timestamps=missing_ts,
        missing_currencies=missing_curr,
        missing_event_names=missing_name,
        missing_actual=missing_act,
        missing_forecast=missing_fcst,
        missing_previous=missing_prev,
        records_by_currency=curr_counts,
        records_by_impact=impact_counts
    )


# ==========================================
# CONTEXT DECISION ENGINE (COLLAPSED)
# ==========================================
from datetime import timedelta

def evaluate_bias(target_event: dict, db: Session) -> tuple[str, str, dict, int]:
    title = target_event.get("event", "").lower()
    target_dt_str = target_event.get("timestamp_utc")
    
    if not target_dt_str:
        return "SKIP", "No valid timestamp on target event", {}, 0

    # Ensure naive dt is aware
    target_dt = datetime.fromisoformat(target_dt_str.replace("Z", "+00:00"))

    precursor_keyword = None
    weight = 0.0

    if "non-farm" in title or "nfp" in title:
        precursor_keyword, weight = "ADP Non-Farm", -1.5
    elif "cpi" in title or "consumer price" in title:
        precursor_keyword, weight = "ISM Services", -1.0
    elif "ppi" in title or "producer price" in title:
        precursor_keyword, weight = "CPI", -1.0
    elif "retail" in title:
        precursor_keyword, weight = "Consumer Confidence", -1.5
    elif "fomc" in title or "federal funds" in title or "interest rate" in title:
        precursor_keyword, weight = "CPI", -1.0
    elif "gdp" in title:
        precursor_keyword, weight = "ISM Manufacturing", -1.0
    else:
        return "SKIP", f"No specific precursor model for '{title}'", {}, 0

    # Query DB directly for the latest precursor event
    from .models import EconomicEvent
    precursor_obj = db.query(EconomicEvent).filter(
        EconomicEvent.event.ilike(f"%{precursor_keyword}%"),
        EconomicEvent.timestamp_utc < target_dt_str
    ).order_by(EconomicEvent.timestamp_utc.desc()).first()

    if not precursor_obj:
        return "SKIP", f"Precursor '{precursor_keyword}' not found before event", {}, 0

    def parse_numeric(v):
        if not v: return None
        v_str = str(v).replace("%", "").replace("K", "").replace("M", "").replace("B", "").replace(",", "").strip()
        try: return float(v_str)
        except: return None

    act = parse_numeric(precursor_obj.actual)
    fcs = parse_numeric(precursor_obj.forecast)
    surp = (act - fcs) if (act is not None and fcs is not None) else None

    if surp is None:
        return "SKIP", f"Precursor '{precursor_keyword}' has no actual/forecast surprise", {}, 0

    score = (1 if surp > 0 else (-1 if surp < 0 else 0)) * weight
    
    context = {
        "precursor_event": precursor_obj.event,
        "actual": act,
        "forecast": fcs,
        "previous": parse_numeric(precursor_obj.previous)
    }
    
    decision = "BUY" if score > 0 else ("SELL" if score < 0 else "SKIP")
    reason = f"Precursor '{precursor_obj.event}' surprise={surp} * weight={weight} -> score={score}"
    
    return decision, reason, context, 1


@app.get("/api/v1/decision")
def get_decision(
    target_time: str = Query(..., description="ISO datetime of the event"),
    symbol: str = Query("USD", description="Currency symbol to filter by (e.g. USD, XAUUSD)"),
    db: Session = Depends(get_db)
):
    try:
        if target_time.endswith("Z"):
            target_time = target_time[:-1] + "+00:00"
        target_dt = datetime.fromisoformat(target_time)
        if target_dt.tzinfo is None:
            target_dt = target_dt.replace(tzinfo=timezone.utc)
        target_dt = target_dt.astimezone(timezone.utc)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid target_time format. Use ISO-8601.")

    currency = "USD" if "USD" in symbol.upper() else "USD"

    # Find event
    start_dt = target_dt - timedelta(minutes=5)
    end_dt = target_dt + timedelta(minutes=5)
    
    from .models import EconomicEvent
    
    events = db.query(EconomicEvent).filter(
        EconomicEvent.currency == currency,
        EconomicEvent.timestamp_utc >= start_dt.isoformat(),
        EconomicEvent.timestamp_utc <= end_dt.isoformat()
    ).order_by(EconomicEvent.timestamp_utc.asc()).all()

    if not events:
        return {
            "decision": "SKIP",
            "event": "Unknown",
            "event_timestamp": target_time,
            "currency": currency,
            "facts_used": 0,
            "context": {},
            "reason": "No economic event found at target time",
            "valid_until": (target_dt + timedelta(minutes=5)).isoformat()
        }

    target_event_obj = None
    for e in events:
        if e.timestamp_utc:
            e_dt = datetime.fromisoformat(e.timestamp_utc.replace("Z", "+00:00"))
            if abs((e_dt - target_dt).total_seconds()) < 60:
                target_event_obj = e
                if e.impact == "High":
                    break
    
    if not target_event_obj:
        target_event_obj = events[0]

    te_dict = {
        "event": target_event_obj.event,
        "timestamp_utc": target_event_obj.timestamp_utc,
        "currency": target_event_obj.currency
    }

    decision, reason, context, facts_used = evaluate_bias(te_dict, db)

    return {
        "decision": decision,
        "event": te_dict["event"],
        "event_timestamp": te_dict["timestamp_utc"],
        "currency": te_dict["currency"],
        "facts_used": facts_used,
        "context": context,
        "reason": reason,
        "valid_until": (target_dt + timedelta(minutes=5)).isoformat()
    }
