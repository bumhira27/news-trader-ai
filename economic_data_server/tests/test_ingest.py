import pytest
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import EconomicEvent, IngestionRun, EventRevision
from app.ingest import run_ingestion

@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    yield session
    session.close()

def test_ingestion_idempotency_and_revisions(test_db):
    fixture_path = Path(__file__).resolve().parent.parent / "fixtures" / "forexfactory_2026_08.json"
    assert fixture_path.exists(), "August 2026 fixture must exist"

    start_dt = datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)
    end_dt = datetime(2026, 8, 31, 23, 59, 59, tzinfo=timezone.utc)

    # 1. First Ingestion Run
    res1 = run_ingestion(
        start_date=start_dt,
        end_date=end_dt,
        file_path=str(fixture_path),
        db=test_db
    )
    assert res1["status"] == "success"
    assert res1["records_inserted"] > 0
    initial_inserted = res1["records_inserted"]
    assert res1["records_updated"] == 0

    # Verify rows in database
    count1 = test_db.query(EconomicEvent).count()
    assert count1 == initial_inserted

    # 2. Second Ingestion Run (Same dataset) -> Must be idempotent (0 new inserted)
    res2 = run_ingestion(
        start_date=start_dt,
        end_date=end_dt,
        file_path=str(fixture_path),
        db=test_db
    )
    assert res2["status"] == "success"
    assert res2["records_inserted"] == 0
    assert res2["records_updated"] == 0

    # Verify total count has NOT increased
    count2 = test_db.query(EconomicEvent).count()
    assert count2 == count1

    # 3. Ingestion Runs Logged
    runs = test_db.query(IngestionRun).all()
    assert len(runs) == 2
    assert runs[0].status == "success"
    assert runs[1].status == "success"
