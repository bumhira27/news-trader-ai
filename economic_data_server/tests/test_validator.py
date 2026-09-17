from datetime import datetime, timezone
import pytest
from app.validator import validate_event_record, validate_batch

def test_validator_required_fields():
    valid_record = {
        "source": "forexfactory",
        "source_event_key": "forexfactory|2026-08-07T12:30:00Z|USD|Nonfarm Payrolls",
        "event": "Nonfarm Payrolls",
        "currency": "USD",
        "impact": "High",
        "timestamp_utc": datetime(2026, 8, 7, 12, 30, 0, tzinfo=timezone.utc),
        "actual": "165K",
        "forecast": "150K",
        "previous": "143K"
    }

    # Valid
    ok, err = validate_event_record(valid_record)
    assert ok is True
    assert err is None

    # Missing event
    bad = dict(valid_record, event="")
    ok, err = validate_event_record(bad)
    assert ok is False
    assert "event" in err.lower()

    # Missing currency
    bad = dict(valid_record, currency="")
    ok, err = validate_event_record(bad)
    assert ok is False
    assert "currency" in err.lower()

    # Missing source
    bad = dict(valid_record, source="")
    ok, err = validate_event_record(bad)
    assert ok is False
    assert "source" in err.lower()

    # Missing timestamp
    bad = dict(valid_record, timestamp_utc=None)
    ok, err = validate_event_record(bad)
    assert ok is False
    assert "timestamp" in err.lower()

def test_validator_blank_values_permitted():
    # Pre-release event with actual=None, forecast=None, previous=None is valid
    prerelease = {
        "source": "forexfactory",
        "source_event_key": "forexfactory|2026-08-19T18:00:00Z|USD|FOMC Meeting Minutes",
        "event": "FOMC Meeting Minutes",
        "currency": "USD",
        "impact": "High",
        "timestamp_utc": datetime(2026, 8, 19, 18, 0, 0, tzinfo=timezone.utc),
        "actual": None,
        "forecast": None,
        "previous": None
    }
    ok, err = validate_event_record(prerelease)
    assert ok is True
    assert err is None

def test_validator_duplicate_keys_in_batch():
    record1 = {
        "source": "forexfactory",
        "source_event_key": "forexfactory|2026-08-07T12:30:00Z|USD|Nonfarm Payrolls",
        "event": "Nonfarm Payrolls",
        "currency": "USD",
        "impact": "High",
        "timestamp_utc": datetime(2026, 8, 7, 12, 30, 0, tzinfo=timezone.utc),
    }
    record2 = dict(record1) # duplicate

    valid, rejected = validate_batch([record1, record2])
    assert len(valid) == 1
    assert len(rejected) == 1
    assert "duplicate" in rejected[0][1].lower()

def test_validator_date_boundaries():
    start_bound = datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)
    end_bound = datetime(2026, 8, 31, 23, 59, 59, tzinfo=timezone.utc)

    aug_event = {
        "source": "forexfactory",
        "source_event_key": "forexfactory|2026-08-31T20:00:00Z|USD|Event",
        "event": "Event",
        "currency": "USD",
        "impact": "Low",
        "timestamp_utc": datetime(2026, 8, 31, 20, 0, 0, tzinfo=timezone.utc),
    }
    sep_event = {
        "source": "forexfactory",
        "source_event_key": "forexfactory|2026-09-01T00:00:00Z|USD|Event",
        "event": "Event",
        "currency": "USD",
        "impact": "Low",
        "timestamp_utc": datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc),
    }

    # August event belongs to August
    ok, err = validate_event_record(aug_event, start_date=start_bound, end_date=end_bound)
    assert ok is True

    # September event does not belong to August
    ok, err = validate_event_record(sep_event, start_date=start_bound, end_date=end_bound)
    assert ok is False
    assert "after requested end" in err
