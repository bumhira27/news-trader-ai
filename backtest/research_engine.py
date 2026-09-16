import sys
from pathlib import Path
import polars as pl
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data.load_prices import load_xauusd_prices

# ─── Settings ────────────────────────────────────────────────────────────────
SL_PIPS        = 300
TRAIL_TRIGGER  = 500
TRAIL_STEP     = 200

PRICE_PATHS = [
    r"C:\Users\bumhira27\Downloads\XAUUSD_2024_all.csv",
    r"C:\Users\bumhira27\Downloads\XAUUSD_2025_all.csv",
    r"C:\Users\bumhira27\Downloads\XAUUSD_2026\*.csv",
]

# We removed the hardcoded biases! The engine must now predict them dynamically.
TRINITY_EVENTS = [
    ("2024-01-05 15:30", "NFP"),
    ("2024-01-11 15:30", "CPI"),
    ("2024-01-17 15:30", "Retail Sales"),
    ("2024-02-02 15:30", "NFP"),
    ("2024-02-13 15:30", "CPI"),
    ("2024-02-15 15:30", "Retail Sales"),
    ("2024-03-08 15:30", "NFP"),
    ("2024-03-12 15:32", "CPI"),
    ("2024-03-14 15:30", "Retail Sales"),
    ("2024-04-05 15:30", "NFP"),
    ("2024-04-10 15:30", "CPI"),
    ("2024-04-15 17:06", "Retail Sales"),
    ("2024-05-03 15:30", "NFP"),
    ("2024-05-15 15:30", "CPI"),
    ("2024-05-15 15:30", "Retail Sales"),
    ("2024-06-07 15:30", "NFP"),
    ("2024-06-12 15:30", "CPI"),
    ("2024-06-18 15:30", "Retail Sales"),
    ("2024-07-05 15:30", "NFP"),
    ("2024-07-11 15:30", "CPI"),
    ("2024-07-16 15:30", "Retail Sales"),
    ("2024-08-02 15:30", "NFP"),
    ("2024-08-14 15:30", "CPI"),
    ("2024-08-15 16:00", "Retail Sales"),
    ("2024-09-06 15:30", "NFP"),
    ("2024-09-11 15:30", "CPI"),
    ("2024-09-17 15:30", "Retail Sales"),
    ("2024-10-04 15:30", "NFP"),
    ("2024-10-10 15:30", "CPI"),
    ("2024-10-17 15:30", "Retail Sales"),
    ("2024-11-01 15:30", "NFP"),
    ("2024-11-13 15:30", "CPI"),
    ("2024-11-15 15:30", "Retail Sales"),
    ("2024-12-06 15:30", "NFP"),
    ("2024-12-11 15:30", "CPI"),
    ("2024-12-17 15:30", "Retail Sales"),
    ("2025-01-10 15:30", "NFP"),
    ("2025-01-15 15:30", "CPI"),
    ("2025-01-16 15:30", "Retail Sales"),
    ("2025-02-07 15:30", "NFP"),
    ("2025-02-12 15:30", "CPI"),
    ("2025-02-14 17:34", "Retail Sales"),
    ("2025-03-07 15:30", "NFP"),
    ("2025-03-12 15:30", "CPI"),
    ("2025-03-17 15:48", "Retail Sales"),
    ("2025-04-04 14:45", "NFP"),
]

def load_calendar() -> pl.DataFrame:
    try:
        return pl.read_parquet("data/calendar_usd_high.parquet")
    except Exception as e:
        print(f"Could not load calendar data: {e}")
        return pl.DataFrame()

def get_event_data(cal_df: pl.DataFrame, target_dt: datetime, event_type: str) -> dict:
    if cal_df.height == 0:
        return {}
    
    events_in_window = cal_df.filter(
        (pl.col("timestamp").dt.year() == target_dt.year) & 
        (pl.col("timestamp").dt.month() == target_dt.month) &
        (pl.col("timestamp").dt.day() == target_dt.day)
    )
    
    if event_type == "NFP":
        keyword, precursor_kw = "Non-Farm", "ADP"
    elif event_type == "CPI":
        keyword, precursor_kw = "CPI", "ISM Services"
    elif event_type == "Retail Sales":
        keyword, precursor_kw = "Retail Sales", "Consumer Confidence"
    else:
        keyword, precursor_kw = event_type, None
        
    matched = events_in_window.filter(pl.col("event").str.to_lowercase().str.contains(keyword.lower()))
    
    if matched.height == 0:
        return {}
        
    row = matched.to_dicts()[0]
    
    historical = cal_df.filter(
        (pl.col("event") == row["event"]) & 
        (pl.col("timestamp") < target_dt)
    ).sort("timestamp", descending=True)
    
    prior_surprise = 0.0
    if historical.height > 0:
        prev_row = historical.to_dicts()[0]
        if prev_row["actual"] is not None and prev_row["forecast"] is not None:
            prior_surprise = prev_row["actual"] - prev_row["forecast"]
            
    # Find Precursor for prediction (e.g. ADP for NFP)
    precursor_surprise = 0.0
    precursor_name = "None"
    if precursor_kw:
        prec_df = cal_df.filter(
            (pl.col("event").str.to_lowercase().str.contains(precursor_kw.lower())) & 
            (pl.col("timestamp") < target_dt)
        ).sort("timestamp", descending=True)
        if prec_df.height > 0:
            p_row = prec_df.to_dicts()[0]
            precursor_name = p_row["event"]
            if p_row["actual"] is not None and p_row["forecast"] is not None:
                precursor_surprise = p_row["actual"] - p_row["forecast"]

    return {
        "event_name": row["event"],
        "forecast": row["forecast"],
        "previous": row["previous"],
        "prior_surprise": prior_surprise,
        "precursor_name": precursor_name,
        "precursor_surprise": precursor_surprise
    }

def calculate_atr(df: pl.DataFrame, periods: int = 14) -> float:
    if df.height < periods:
        return 0.0
    df = df.with_columns([pl.col("close").shift(1).alias("prev_close")]).fill_null(strategy="backward")
    df = df.with_columns([
        (pl.col("high") - pl.col("low")).alias("tr1"),
        (pl.col("high") - pl.col("prev_close")).abs().alias("tr2"),
        (pl.col("low") - pl.col("prev_close")).abs().alias("tr3"),
    ])
    df = df.with_columns([pl.max_horizontal(["tr1", "tr2", "tr3"]).alias("tr")])
    return df["tr"].tail(periods).mean() * 100

def get_mfe_mae(entry_price, high, low, bias):
    if bias == "BUY":
        return (high - entry_price) * 100, (entry_price - low) * 100
    else:
        return (entry_price - low) * 100, (high - entry_price) * 100

def run():
    prices = load_xauusd_prices(PRICE_PATHS)
    cal_df = load_calendar()

    print("==================================================")
    print("AUTHORITATIVE RESEARCH ENGINE")
    print("Strictly separated Pre-News vs Post-News context.")
    print("==================================================\n")

    for dt_str, event_type in TRINITY_EVENTS:
        event_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
        
        cal_features = get_event_data(cal_df, event_dt, event_type)
        if not cal_features:
            continue
            
        ts = pl.col("timestamp")
        pre_news_window = prices.filter((ts >= event_dt - timedelta(minutes=15)) & (ts < event_dt))
        if pre_news_window.height == 0:
            continue
            
        entry_price = pre_news_window["close"][-1]
        pre_range = (pre_news_window["high"].max() - pre_news_window["low"].min()) * 100
        pre_trend = "Bullish" if entry_price >= pre_news_window["open"][0] else "Bearish"
        atr = calculate_atr(pre_news_window, 14)
        
        # ─── PREDICTION (Based strictly on pre-news precursor) ───
        ps = cal_features["precursor_surprise"]
        if ps > 0:
            bias = "BUY" if event_type in ["CPI", "Retail Sales"] else "SELL"
        elif ps < 0:
            bias = "SELL" if event_type in ["CPI", "Retail Sales"] else "BUY"
        else:
            bias = "NO TRADE"
            
        # NFP inverse logic mapped to original blueprint
        if event_type == "NFP":
            if ps > 0: bias = "SELL"
            elif ps < 0: bias = "BUY"
            
        # ─── SEQUENTIAL POST-NEWS SIMULATION ───
        # This solves the OHLC path problem by stepping minute-by-minute
        post_news_window = prices.filter((ts >= event_dt) & (ts < event_dt + timedelta(minutes=15)))
        
        mfe_1m, mae_1m = 0.0, 0.0
        mfe_5m, mae_5m = 0.0, 0.0
        
        hit_sl = False
        hit_trigger = False
        trail_survived = False
        final_pips = 0.0
        
        running_mfe = 0.0
        running_mae = 0.0
        
        minutes_elapsed = 0
        for row in post_news_window.to_dicts():
            minutes_elapsed += 1
            bar_mfe, bar_mae = get_mfe_mae(entry_price, row["high"], row["low"], bias)
            
            if bar_mfe > running_mfe: running_mfe = bar_mfe
            if bar_mae > running_mae: running_mae = bar_mae
                
            if minutes_elapsed == 1:
                mfe_1m, mae_1m = running_mfe, running_mae
            if minutes_elapsed == 5:
                mfe_5m, mae_5m = running_mfe, running_mae
                
            # If trade is already closed, just continue updating MFE/MAE for analytics
            if hit_sl or trail_survived:
                continue
                
            # Worst-case assumption: If a single 1M bar hits SL, it hit SL first.
            if bar_mae >= SL_PIPS:
                hit_sl = True
                final_pips = -SL_PIPS
                continue
                
            if bar_mfe >= TRAIL_TRIGGER:
                hit_trigger = True
                # If trail triggers, we assume it closes at Trigger - Step in the worst case, 
                # or we lock it in at the bar close if it didn't retrace the full step.
                # For simplicity, if trigger hits, we consider it a trail survival victory.
                trail_survived = True
                final_pips = bar_mfe - TRAIL_STEP
                
        if not hit_sl and not trail_survived and post_news_window.height > 0:
            last_bar = post_news_window.to_dicts()[-1]
            if bias == "BUY":
                final_pips = (last_bar["close"] - entry_price) * 100
            else:
                final_pips = (entry_price - last_bar["close"]) * 100

        # Output exactly as requested by user
        print(f"EVENT:              {cal_features['event_name']}")
        print(f"TIMESTAMP:          {dt_str}")
        print(f"EVENT_TYPE:         {event_type}")
        print("\nPRE-NEWS FEATURES")
        print(f"forecast:           {cal_features['forecast']}")
        print(f"previous:           {cal_features['previous']}")
        print(f"prior_surprise:     {cal_features['prior_surprise']:+.2f}")
        print(f"precursor_surprise: {ps:+.2f} ({cal_features['precursor_name']})")
        print(f"pre_news_price:     {entry_price:.2f}")
        print(f"pre_news_range:     {pre_range:.1f}")
        print(f"pre_news_trend:     {pre_trend}")
        print(f"ATR:                {atr:.1f}")
        print(f"spread:             0.25 (Simulated)")
        print(f"DXY:                N/A (Requires data feed)")
        print(f"US10Y:              N/A (Requires data feed)")
        
        print("\nMODEL")
        print(f"prediction:         {bias}")
        print(f"confidence:         N/A")
        
        print("\nPOST-NEWS LABELS")
        print(f"MFE_1m:             {mfe_1m:+.1f}")
        print(f"MFE_5m:             {mfe_5m:+.1f}")
        print(f"hit_SL:             {'YES' if hit_sl else 'NO'}")
        print(f"hit_trigger:        {'YES' if hit_trigger else 'NO'}")
        print(f"trail_survival:     {'YES' if trail_survived else 'NO'}")
        print(f"final_pnl:          {final_pips:+.2f} pips")
        print("-" * 50)

if __name__ == "__main__":
    run()
