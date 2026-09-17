import os

# The application now requires an explicit DATABASE_URL. Tests use an isolated
# SQLite database and override the application's database dependency below.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.ingest import run_ingestion
from app.main import app


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
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
    end_dt = datetime(2026, 8, 31, 23, 59, 59, 999999, tzinfo=timezone.utc)
    run_ingestion(start_date=start_dt, end_date=end_dt, file_path=str(fixture_path), db=db)
    db.close()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "economic_data_server"
    assert data["database"] == "connected"


def test_get_events_filtering(client):
    response = client.get("/api/v1/events?currency=USD&impact=High")
    assert response.status_code == 200
    events = response.json()
    assert len(events) > 0
    for event in events:
        assert event["currency"] == "USD"
        assert event["impact"] == "High"

    search_response = client.get("/api/v1/events?event=Payrolls")
    assert search_response.status_code == 200
    search_events = search_response.json()
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
    for event in events:
        assert event["timestamp_utc"].startswith("2026-08")


def test_single_event_endpoint(client):
    events_response = client.get("/api/v1/events?limit=1")
    event_id = events_response.json()[0]["id"]

    response = client.get(f"/api/v1/events/{event_id}")
    assert response.status_code == 200
    event = response.json()
    assert event["id"] == event_id

    not_found = client.get("/api/v1/events/999999")
    assert not_found.status_code == 404


def test_news_events_endpoint(client):
    response = client.get("/api/v1/news-events?currency=USD")
    assert response.status_code == 200
    events = response.json()
    assert len(events) > 0
    for event in events:
        assert event["currency"] == "USD"
        assert event["impact"] == "High"


def test_validation_report_endpoint(client):
    response = client.get("/api/v1/validation-report?year=2026&month=8")
    assert response.status_code == 200
    report = response.json()
    assert report["total_records"] > 0
    assert report["unique_records"] == report["total_records"]
    assert report["duplicate_records"] == 0
    assert report["missing_timestamps"] == 0
    assert report["missing_currencies"] == 0
    assert report["missing_event_names"] == 0
    assert "USD" in report["records_by_currency"]
    assert "High" in report["records_by_impact"]
