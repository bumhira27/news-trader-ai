from datetime import datetime, timezone
import pytest
from data.context_engine import ContextEngine, parse_numeric_val
import scoring.event_classifier as ec
import scoring.surprise_scorer as ss
import scoring.multi_factor_scorecard as ms

def test_parse_numeric_val():
    assert parse_numeric_val("3.7%") == 3.7
    assert parse_numeric_val("245K") == 245000.0
    assert parse_numeric_val("1.2M") == 1200000.0
    assert parse_numeric_val("-0.4%") == -0.4
    assert parse_numeric_val("54.1") == 54.1
    assert parse_numeric_val(None) is None
    assert parse_numeric_val("") is None

def test_context_engine_derived_metrics():
    engine = ContextEngine()
    # Surprise: actual - forecast
    surp = engine.calculate_surprise("165K", "150K")
    assert surp == 15000.0

    surp_pct = engine.calculate_surprise("3.2%", "3.0%")
    assert round(surp_pct, 2) == 0.2

    # Deviation: forecast - previous
    dev = engine.calculate_forecast_deviation("150K", "143K")
    assert dev == 7000.0

def test_context_engine_fomc_context_fallback():
    sample_events = [
        {
            "event": "Nonfarm Payrolls",
            "timestamp_utc": "2026-08-07T12:30:00Z",
            "actual": "165K",
            "forecast": "150K",
            "previous": "143K",
            "_dt": datetime(2026, 8, 7, 12, 30, 0, tzinfo=timezone.utc)
        },
        {
            "event": "CPI m/m",
            "timestamp_utc": "2026-08-12T12:30:00Z",
            "actual": "0.2%",
            "forecast": "0.2%",
            "previous": "0.1%",
            "_dt": datetime(2026, 8, 12, 12, 30, 0, tzinfo=timezone.utc)
        }
    ]
    engine = ContextEngine(fallback_events=sample_events)
    context_str = engine.build_fomc_context("2026-08-19T18:00:00Z")
    assert "Previous CPI:" in context_str
    assert "Previous NFP:" in context_str
    assert "Actual = 165K" in context_str
    assert "Actual = 0.2%" in context_str

def test_event_classifier():
    cpi = ec.classify_event("Core CPI m/m")
    assert cpi["category"] == "inflation"

    nfp = ec.classify_event("Non-Farm Employment Change")
    assert nfp["category"] == "labor"

    gdp = ec.classify_event("Prelim GDP q/q")
    assert gdp["category"] == "growth"

    claims = ec.classify_event("Jobless Claims")
    assert claims["category"] == "labor"

    # Bias test
    bias, conf = ec.get_bias("CPI m/m", actual=3.5, forecast=3.0, previous=2.8)
    assert bias == "SELL" # higher inflation = bearish gold / buy USD
    assert conf > 0

def test_surprise_scorer():
    s = ss.score_surprise(actual=165, forecast=150, previous=143)
    assert s > 0

def test_macro_scorecard():
    scorecard = ms.MacroScorecard()
    res = scorecard.generate_pre_release_scorecard(
        cpi_forecast=3.5,
        cpi_previous=3.0,
        growth_forecast=52.0,
        growth_previous=50.0
    )
    assert "factors" in res
    assert res["bias"] in ("BUY", "SELL", "SKIP")
