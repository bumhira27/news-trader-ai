from datetime import datetime, timezone

from app.normalizer import (
    build_source_event_key,
    normalize_currency,
    normalize_event_name,
    normalize_event_record,
    normalize_impact,
    normalize_raw_value,
    normalize_timestamp,
)


def test_normalize_raw_value():
    assert normalize_raw_value("3.7%") == "3.7%"
    assert normalize_raw_value("245K") == "245K"
    assert normalize_raw_value("1.2M") == "1.2M"
    assert normalize_raw_value("-0.4%") == "-0.4%"
    assert normalize_raw_value("  150K  ") == "150K"
    assert normalize_raw_value(None) is None
    assert normalize_raw_value("") is None
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
    assert normalize_impact("Med") == "Medium"
    assert normalize_impact("Low") == "Low"
    assert normalize_impact("Holiday") == "Non-Economic"
    assert normalize_impact(None) == "Low"


def test_normalize_timestamp_iso():
    assert normalize_timestamp("2026-08-07T12:30:00Z") == datetime(
        2026, 8, 7, 12, 30, tzinfo=timezone.utc
    )
    assert normalize_timestamp("2026-08-07T08:30:00-04:00") == datetime(
        2026, 8, 7, 12, 30, tzinfo=timezone.utc
    )


def test_normalize_timestamp_components_with_dst():
    # August is EDT (UTC-4), while January is EST (UTC-5).
    august = normalize_timestamp(
        "08-07-2026",
        "8:30am",
        source_timezone_name="America/New_York",
    )
    january = normalize_timestamp(
        "01-07-2026",
        "8:30am",
        source_timezone_name="America/New_York",
    )

    assert august == datetime(2026, 8, 7, 12, 30, tzinfo=timezone.utc)
    assert january == datetime(2026, 1, 7, 13, 30, tzinfo=timezone.utc)


def test_naive_iso_requires_explicit_source_timezone():
    ts = normalize_timestamp(
        "2026-01-07T08:30:00",
        source_timezone_name="America/New_York",
    )
    assert ts == datetime(2026, 1, 7, 13, 30, tzinfo=timezone.utc)


def test_build_source_event_key():
    ts = datetime(2026, 8, 7, 12, 30, tzinfo=timezone.utc)
    assert build_source_event_key(
        "forexfactory", ts, "USD", "Nonfarm Payrolls"
    ) == "forexfactory|2026-08-07T12:30:00Z|USD|Nonfarm Payrolls"


def test_normalize_event_record():
    raw = {
        "title": " Nonfarm Payrolls ",
        "country": "USD",
        "date": "2026-08-07T08:30:00-04:00",
        "impact": "High",
        "actual": "165K",
        "forecast": "150K",
        "previous": "143K",
    }

    normalized = normalize_event_record(raw, source="forexfactory")

    assert normalized["source"] == "forexfactory"
    assert normalized["event"] == "Nonfarm Payrolls"
    assert normalized["currency"] == "USD"
    assert normalized["impact"] == "High"
    assert normalized["timestamp_utc"] == datetime(
        2026, 8, 7, 12, 30, tzinfo=timezone.utc
    )
    assert normalized["actual"] == "165K"
    assert normalized["forecast"] == "150K"
    assert normalized["previous"] == "143K"
    assert normalized["source_event_key"] == (
        "forexfactory|2026-08-07T12:30:00Z|USD|Nonfarm Payrolls"
    )
