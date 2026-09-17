import pytest
from datetime import datetime, timezone
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import app
from app.ingest import run_ingestion

from sqlalchemy.pool import StaticPool

# Setup test DB engine with StaticPool so all connections share the in-memory database
engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(scope="module", autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    fixture_path = Path(__file__).resolve().parent.parent / "fixtures" / "forexfactory_2026_08.json"
    start_dt = datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)
    end_dt = datetime(2026, 8, 31, 23, 59, 59, tzinfo=timezone.utc)
    run_ingestion(start_date=start_dt, end_date=end_dt, file_path=str(fixture_path), db=db)
    db.close()
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def client():
    return TestClient(app)

def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "economic_data_server"
    assert data["database"] == "connected"

def test_get_events_filtering(client):
    # Filter USD High impact
    response = client.get("/api/v1/events?currency=USD&impact=High")
    assert response.status_code == 200
    events = response.json()
    assert len(events) > 0
    for e in events:
        assert e["currency"] == "USD"
        assert e["impact"] == "High"

    # Search event keyword
    res_search = client.get("/api/v1/events?event=Payrolls")
    assert res_search.status_code == 200
    search_events = res_search.json()
    assert len(search_events) == 1
    assert "Nonfarm Payrolls" in search_events[0]["event"]
    assert search_events[0]["actual"] == "165K"
    assert search_events[0]["forecast"] == "150K"
    assert search_events[0]["previous"] == "143K"

def test_monthly_calendar_endpoint(client):
    response = client.get("/api/v1/calendar/2026/8")
    assert response.status_code == 200
    events = response.json()
    assert len(events) > 0
    for e in events:
        assert e["timestamp_utc"].startswith("2026-08")

def test_single_event_endpoint(client):
    events_res = client.get("/api/v1/events?limit=1")
    event_id = events_res.json()[0]["id"]

    response = client.get(f"/api/v1/events/{event_id}")
    assert response.status_code == 200
    e = response.json()
    assert e["id"] == event_id

    # 404 for nonexistent
    res_404 = client.get("/api/v1/events/999999")
    assert res_404.status_code == 404

def test_news_events_endpoint(client):
    response = client.get("/api/v1/news-events?currency=USD")
    assert response.status_code == 200
    events = response.json()
    assert len(events) > 0
    for e in events:
        assert e["currency"] == "USD"
        assert e["impact"] == "High"

def test_validation_report_endpoint(client):
    response = client.get("/api/v1/validation-report?year=2026&month=8")
    assert response.status_code == 200
    rep = response.json()
    assert rep["total_records"] > 0
    assert rep["unique_records"] == rep["total_records"]
    assert rep["duplicate_records"] == 0
    assert rep["missing_timestamps"] == 0
    assert rep["missing_currencies"] == 0
    assert rep["missing_event_names"] == 0
    assert "USD" in rep["records_by_currency"]
    assert "High" in rep["records_by_impact"]
