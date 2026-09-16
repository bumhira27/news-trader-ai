"""
Backtesting engine for news trading strategies on XAUUSD.
Evaluates Pre-Release Bias predictions.
"""
import sys
from pathlib import Path
import polars as pl
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.load_prices import load_xauusd_prices, measure_post_event_move
from scoring.multi_factor_scorecard import MacroScorecard

WINDOWS = [5, 15, 30, 60]
MIN_PIP_THRESHOLD = 50

def align_events_with_prices(calendar: pl.DataFrame, prices: pl.DataFrame, tolerance_minutes: int = 5) -> pl.DataFrame:
    cal, pr = calendar.clone(), prices.clone()
    if "datetime" in cal.columns and "timestamp" not in cal.columns:
        cal = cal.rename({"datetime": "timestamp"})
    for target, label in [(cal, "cal"), (pr, "pr")]:
        schema_type = target.schema.get("timestamp")
        if schema_type in (pl.String, pl.Utf8):
            if label == "cal": cal = cal.with_columns(pl.col("timestamp").str.to_datetime(strict=False))
            else: pr = pr.with_columns(pl.col("timestamp").str.to_datetime(strict=False))
        schema_type = target.schema.get("timestamp")
        if schema_type is not None and hasattr(schema_type, "time_zone") and schema_type.time_zone is not None:
            if label == "cal": cal = cal.with_columns(pl.col("timestamp").dt.replace_time_zone(None))
            else: pr = pr.with_columns(pl.col("timestamp").dt.replace_time_zone(None))

    cal, pr = cal.sort("timestamp"), pr.sort("timestamp")
    price_cols = [c for c in ["timestamp", "open", "high", "low", "close", "volume"] if c in pr.columns]
    aligned = cal.join_asof(pr.select(price_cols), on="timestamp", strategy="backward", tolerance=f"{tolerance_minutes}m")
    return aligned.filter(pl.col("close").is_not_null())

def _compute_mfe_mae_for_row(row: dict, prices: pl.DataFrame) -> dict:
    event_time = row["timestamp"]
    direction = row.get("predicted_direction", "SKIP")
    if direction == "SKIP" or event_time is None:
        return {f"mfe_{w}m": None for w in WINDOWS} | {f"mae_{w}m": None for w in WINDOWS}
    dir_lower = "buy" if direction == "BUY" else "sell"
    return measure_post_event_move(prices, event_time, dir_lower, WINDOWS)

def _attach_mfe_mae(events: pl.DataFrame, prices: pl.DataFrame) -> pl.DataFrame:
    if events.height == 0: return events
    mfe_mae_rows = [_compute_mfe_mae_for_row(r, prices) for r in events.to_dicts()]
    combined = pl.concat([events, pl.DataFrame(mfe_mae_rows)], how="horizontal_extend")
    for w in WINDOWS:
        col = f"mfe_{w}m"
        combined = combined.with_columns(
            pl.when(pl.col(col).is_not_null() & (pl.col(col) > MIN_PIP_THRESHOLD))
            .then(pl.lit(True)).otherwise(pl.lit(False)).alias(f"correct_{w}m")
        )
    return combined

def filter_target_events(events: pl.DataFrame) -> pl.DataFrame:
    targets = ["CPI", "Non-Farm", "PCE", "ISM", "Retail Sales", "Unemployment Claims", "Federal Funds Rate"]
    regex = "(?i)" + "|".join(targets)
    return events.filter(pl.col("event").str.contains(regex))

def backtest_pre_release_scorecard(events: pl.DataFrame, prices: pl.DataFrame, macro_context: pl.DataFrame) -> pl.DataFrame:
    scorecard = MacroScorecard()
    events = events.join_asof(macro_context, on="timestamp", strategy="backward")
    rows = events.to_dicts()
    
    for row in rows:
        forecast = row.get("forecast")
        previous = row.get("previous")
        event_name = row.get("event", "").lower()
        
        kwargs = {
            "current_rate": row.get("fedfunds_rate", 5.33),
            "us10y_yield": row.get("us10y_yield", 4.2),
        }
        
        if forecast is not None and previous is not None:
            if "cpi" in event_name or "pce" in event_name:
                kwargs["cpi_forecast"] = forecast
                kwargs["cpi_previous"] = previous
            elif "non-farm" in event_name:
                kwargs["nfp_forecast"] = forecast
                kwargs["nfp_previous"] = previous
            elif "claims" in event_name:
                kwargs["claims_forecast"] = forecast
                kwargs["claims_previous"] = previous
            elif "ism" in event_name or "retail" in event_name:
                kwargs["growth_forecast"] = forecast
                kwargs["growth_previous"] = previous
            elif "federal funds" in event_name or "fomc" in event_name:
                kwargs["expected_rate"] = forecast
                
        result = scorecard.generate_pre_release_scorecard(**kwargs)
        row["scorecard_total"] = result["total_score"]
        row["predicted_direction"] = result["bias"]
        
    df = pl.DataFrame(rows).filter((pl.col("scorecard_total").abs() > 1.0) & (pl.col("predicted_direction") != "SKIP"))
    return _attach_mfe_mae(df, prices)

def summarize_results(results: pl.DataFrame, approach_name: str) -> dict:
    n = results.height
    if n == 0:
        return {"approach": approach_name, "total_trades": 0, "win_rate_5m": 0.0, "win_rate_15m": 0.0, "win_rate_30m": 0.0, "win_rate_60m": 0.0, "avg_mfe_30m": 0.0, "avg_mae_30m": 0.0, "profit_factor_30m": 0.0}
    def wr(col: str):
        s = results[col].sum()
        return float(s) / n if s is not None else 0.0
    avg_mfe = float(results["mfe_30m"].drop_nulls().mean() or 0.0)
    avg_mae = float(results["mae_30m"].drop_nulls().mean() or 0.0)
    pf = avg_mfe / avg_mae if avg_mae > 0 else 0.0
    return {"approach": approach_name, "total_trades": n, "win_rate_5m": wr("correct_5m"), "win_rate_15m": wr("correct_15m"), "win_rate_30m": wr("correct_30m"), "win_rate_60m": wr("correct_60m"), "avg_mfe_30m": round(avg_mfe, 2), "avg_mae_30m": round(avg_mae, 2), "profit_factor_30m": round(pf, 2)}

def map_event_category(event_name: str) -> str:
    name = event_name.lower()
    if "cpi" in name: return "CPI"
    if "pce" in name: return "PCE"
    if "non-farm" in name: return "NFP"
    if "ism" in name: return "ISM"
    if "retail" in name: return "Retail Sales"
    if "claims" in name: return "Jobless Claims"
    if "federal funds" in name or "fomc" in name: return "FOMC"
    return "Other"

if __name__ == "__main__":
    try: from tabulate import tabulate
    except ImportError: tabulate = None

    project_root = Path(__file__).resolve().parent.parent
    calendar_path = project_root / "data" / "calendar_usd_high.parquet"
    macro_path = project_root / "data" / "macro_context.parquet"
    
    price_paths = [
        r"C:\Users\bumhira27\Downloads\XAUUSD_2024_all.csv",
        r"C:\Users\bumhira27\Downloads\XAUUSD_2025_all.csv",
        r"C:\Users\bumhira27\Downloads\XAUUSD_2026\*.csv"
    ]

    print("Loading calendar data...")
    calendar = pl.read_parquet(calendar_path)
    print(f"  {calendar.height} total USD high-impact events loaded")
    
    calendar = filter_target_events(calendar)
    print(f"  {calendar.height} targeted events remaining")
    
    print("Loading FRED macro data...")
    macro_context = pl.read_parquet(macro_path)

    print("Loading price data...")
    prices = load_xauusd_prices(price_paths)
    print(f"  {prices.height} bars ({prices['timestamp'].min()} to {prices['timestamp'].max()})")

    print("Aligning events with prices...")
    aligned = align_events_with_prices(calendar, prices)
    print(f"  {aligned.height} targeted events matched to price data")

    res_score = backtest_pre_release_scorecard(aligned, prices, macro_context)

    res_score = res_score.with_columns(
        pl.col("event").map_elements(map_event_category, return_dtype=pl.Utf8).alias("event_category")
    )

    summary = [
        summarize_results(res_score, "ALL TARGET EVENTS (Aggregate)")
    ]
    
    categories = ["CPI", "NFP", "PCE", "ISM", "Retail Sales", "Jobless Claims", "FOMC"]
    for cat in categories:
        cat_df = res_score.filter(pl.col("event_category") == cat)
        if cat_df.height > 0:
            summary.append(summarize_results(cat_df, f"  -> {cat}"))

    print("\n========== RESULTS PER EVENT CATEGORY ==========")
    if tabulate: print(tabulate(summary, headers="keys", floatfmt=".2f"))
    else:
        for s in summary: print(s)
