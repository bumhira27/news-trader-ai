import uvicorn
from fastapi import FastAPI, HTTPException, Query
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from .context_engine import ContextEngine

app = FastAPI(title="Context Engine API", version="1.0.0")
engine = ContextEngine()

@app.get("/api/v1/decision")
def get_decision(
    target_time: str = Query(..., description="ISO datetime of the event"),
    symbol: str = Query("USD", description="Currency symbol to filter by (e.g. USD, XAUUSD)")
):
    try:
        # target_time comes in as a naive or aware ISO string. Convert to aware UTC.
        if target_time.endswith("Z"):
            target_time = target_time[:-1] + "+00:00"
        target_dt = datetime.fromisoformat(target_time)
        if target_dt.tzinfo is None:
            target_dt = target_dt.replace(tzinfo=timezone.utc)
        target_dt = target_dt.astimezone(timezone.utc)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid target_time format. Use ISO-8601.")

    currency = "USD"
    if "USD" in symbol.upper():
        currency = "USD"

    start_dt = target_dt - timedelta(minutes=5)
    end_dt = target_dt + timedelta(minutes=5)
    
    events = engine.fetch_events(
        currency=currency,
        start=start_dt.isoformat(),
        end=end_dt.isoformat(),
        limit=10
    )

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

    target_event = None
    for e in events:
        e_time = e.get("timestamp_utc")
        if e_time:
            e_dt = datetime.fromisoformat(e_time.replace("Z", "+00:00"))
            if abs((e_dt - target_dt).total_seconds()) < 60:
                target_event = e
                if e.get("impact") == "High":
                    break

    if not target_event:
        target_event = events[0]

    decision, reason, context, facts_used = engine.evaluate_bias(target_event)

    return {
        "decision": decision,
        "event": target_event.get("event"),
        "event_timestamp": target_event.get("timestamp_utc"),
        "currency": target_event.get("currency"),
        "facts_used": facts_used,
        "context": context,
        "reason": reason,
        "valid_until": (target_dt + timedelta(minutes=5)).isoformat()
    }

if __name__ == "__main__":
    uvicorn.run("data.api:app", host="127.0.0.1", port=8001, reload=True)
