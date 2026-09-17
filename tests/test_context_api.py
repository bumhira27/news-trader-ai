from fastapi.testclient import TestClient
from data.api import app, engine
from datetime import datetime, timezone
import pytest

client = TestClient(app)

def test_get_decision_no_event(monkeypatch):
    # Mock engine.fetch_events to return []
    monkeypatch.setattr(engine, "fetch_events", lambda **kwargs: [])
    
    res = client.get("/api/v1/decision?target_time=2026-09-18T14:30:00Z&symbol=USD")
    assert res.status_code == 200
    data = res.json()
    assert data["decision"] == "SKIP"
    assert data["reason"] == "No economic event found at target time"

def test_get_decision_nfp_buy(monkeypatch):
    target_time = "2026-09-18T14:30:00+00:00"
    
    def mock_fetch_events(**kwargs):
        return [{
            "event": "Non-Farm Employment Change",
            "timestamp_utc": target_time,
            "currency": "USD",
            "impact": "High"
        }]
        
    def mock_evaluate_bias(target_event):
        return "BUY", "NFP buy reason", {"precursor_event": "ADP Non-Farm", "surprise": 100}, 1
        
    monkeypatch.setattr(engine, "fetch_events", mock_fetch_events)
    monkeypatch.setattr(engine, "evaluate_bias", mock_evaluate_bias)
    
    res = client.get("/api/v1/decision?target_time=2026-09-18T14:30:00Z&symbol=USD")
    assert res.status_code == 200
    data = res.json()
    assert data["decision"] == "BUY"
    assert data["event"] == "Non-Farm Employment Change"
    assert data["facts_used"] == 1
    assert data["context"]["surprise"] == 100
