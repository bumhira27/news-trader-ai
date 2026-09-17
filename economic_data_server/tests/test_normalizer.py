from datetime import datetime, timezone
import pytest
from app.normalizer import (
    normalize_raw_value,
    normalize_currency,
    normalize_impact,
    normalize_event_name,
    normalize_timestamp,
    build_source_event_key,
    normalize_event_record
)

def test_normalize_raw_value():
    assert normalize_raw_value("3.7%") == "3.7%"
    assert normalize_raw_value("245K") == "245K"
    assert normalize_raw_value("1.2M") == "1.2M"
    assert normalize_raw_value("-0.4%") == "-0.4%"
    assert normalize_raw_value("54.1") == "54.1"
    assert normalize_raw_value("4.00%") == "4.00%"
    assert normalize_raw_value("  150K  ") == "150K"
    assert normalize_raw_value(None) is None
    assert normalize_raw_value("") is None
    assert normalize_raw_value("   ") is None
    assert normalize_raw_value("None") is None
    assert normalize_raw_value("NaN") is None
    assert normalize_raw_value("-") is None

def test_normalize_currency():
    assert normalize_currency("usd") == "USD"
    assert normalize_currency(" EUR ") == "EUR"
    assert normalize_currency(None) == "USD"

def test_normalize_impact():
    assert normalize_impact("High") == "High"
    assert normalize_impact("high impact expected") == "High"
    assert normalize_impact("Medium") == "Medium"
    assert normalize_impact("Low") == "Low"
    assert normalize_impact("Holiday") == "Non-Economic"
    assert normalize_impact(None) == "Low"

def test_normalize_timestamp_iso():
    ts = normalize_timestamp("2026-08-07T12:30:00Z")
    assert ts == datetime(2026, 8, 7, 12, 30, 0, tzinfo=timezone.utc)

    # Offset conversion to UTC
    ts_offset = normalize_timestamp("2026-08-07T08:30:00-04:00")
    assert ts_offset == datetime(2026, 8, 7, 12, 30, 0, tzinfo=timezone.utc)

def test_normalize_timestamp_components():
    # Date MM-DD-YYYY and time 8:30am with Eastern default offset (-4)
    ts = normalize_timestamp("08-07-2026", "8:30am")
    assert ts == datetime(2026, 8, 7, 12, 30, 0, tzinfo=timezone.utc)

def test_build_source_event_key():
    ts = datetime(2026, 8, 7, 12, 30, 0, tzinfo=timezone.utc)
    key = build_source_event_key("forexfactory", ts, "USD", "Nonfarm Payrolls")
    assert key == "forexfactory|2026-08-07T12:30:00Z|USD|Nonfarm Payrolls"

def test_normalize_event_record():
    raw = {
        "title": " Nonfarm Payrolls ",
        "country": "USD",
        "date": "2026-08-07T08:30:00-04:00",
        "impact": "High",
        "actual": "165K",
        "forecast": "150K",
        "previous": "143K"
    }
    norm = normalize_event_record(raw, source="forexfactory")
    assert norm["source"] == "forexfactory"
    assert norm["event"] == "Nonfarm Payrolls"
    assert norm["currency"] == "USD"
    assert norm["impact"] == "High"
    assert norm["timestamp_utc"] == datetime(2026, 8, 7, 12, 30, 0, tzinfo=timezone.utc)
    assert norm["actual"] == "165K"
    assert norm["forecast"] == "150K"
    assert norm["previous"] == "143K"
    assert norm["source_event_key"] == "forexfactory|2026-08-07T12:30:00Z|USD|Nonfarm Payrolls"
