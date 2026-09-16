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

# ─── TRINITY EVENTS MAPPING ──────────────────────────────────────────────────
# IMPORTANT: We manually supply the exact timestamps here because the 
# open-source HuggingFace dataset (Ehsanrs2/Forex_Factory_Calendar) strips 
# the hour/minute component (setting them to 00:00) for major events like NFP.
# These timestamps are the canonical SAST release times for these events, 
# NOT execution times. All weird minute offsets have been normalized to exactly 15:30.
TRINITY_EVENTS = [
    ("2024-01-05 15:30", "NFP"),
    ("2024-01-11 15:30", "CPI"),
    ("2024-01-17 15:30", "Retail Sales"),
    ("2024-02-02 15:30", "NFP"),
    ("2024-02-13 15:30", "CPI"),
    ("2024-02-15 15:30", "Retail Sales"),
    ("2024-03-08 15:30", "NFP"),
    ("2024-03-12 15:30", "CPI"),
    ("2024-03-14 15:30", "Retail Sales"),
    ("2024-04-05 15:30", "NFP"),
    ("2024-04-10 15:30", "CPI"),
    ("2024-04-15 15:30", "Retail Sales"),
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
    ("2024-08-15 15:30", "Retail Sales"),
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
    ("2025-02-14 15:30", "Retail Sales"),
    ("2025-03-07 15:30", "NFP"),
    ("2025-03-12 15:30", "CPI"),
    ("2025-03-17 15:30", "Retail Sales"),
    ("2025-04-04 15:30", "NFP"),
]

def load_calendar() -> pl.DataFrame:
    try:
        return pl.read_parquet("data/calendar_usd_high.parquet")
    except Exception as e:
        print(f"Could not load calendar data: {e}")
        return pl.DataFrame()

def get_precursor_data(cal_df: pl.DataFrame, target_dt: datetime, event_type: str) -> dict:
    if event_type == "NFP":
        precursor_kw = "ADP"
    elif event_type == "CPI":
        precursor_kw = "ISM Services"
    elif event_type == "Retail Sales":
        precursor_kw = "Consumer Confidence"
    else:
        precursor_kw = None
        
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
    print("Canonical exact timestamps used.")
    print("==================================================\n")

    for dt_str, event_type in TRINITY_EVENTS:
        event_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
        
        # Get precursor data
        cal_features = get_precursor_data(cal_df, event_dt, event_type)
        
        # Manually query historical targets to get prior surprise (since we don't have target event_name dynamically easily, we'll map it)
        if event_type == "NFP": event_name = "Non-Farm Employment Change"
        elif event_type == "CPI": event_name = "CPI m/m"
        else: event_name = "Retail Sales m/m"
        
        historical = cal_df.filter(
            (pl.col("event") == event_name) & 
            (pl.col("timestamp") < event_dt)
        ).sort("timestamp", descending=True)
        
        prior_surprise = 0.0
        forecast = 0.0
        previous = 0.0
        if historical.height > 0:
            prev_row = historical.to_dicts()[0]
            if prev_row["actual"] is not None and prev_row["forecast"] is not None:
                prior_surprise = prev_row["actual"] - prev_row["forecast"]
            forecast = prev_row["forecast"] if prev_row["forecast"] else 0.0
            previous = prev_row["previous"] if prev_row["previous"] else 0.0
                
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
        post_news_window = prices.filter((ts >= event_dt) & (ts < event_dt + timedelta(minutes=15)))
        
        mfe_1m, mae_1m = 0.0, 0.0
        mfe_5m, mae_5m = 0.0, 0.0
        
        trail_sl = -SL_PIPS
        trade_active = True
        hit_sl = False
        hit_trigger = False
        trail_survived = False
        intrabar_collision = False
        final_pips = 0.0
        
        running_mfe = 0.0
        running_mae = 0.0
        
        minutes_elapsed = 0
        for p_row in post_news_window.to_dicts():
            minutes_elapsed += 1
            
            # Calculate pips relative to entry for this M1 bar
            if bias == "BUY":
                pips_high = (p_row["high"] - entry_price) * 100
                pips_low = (p_row["low"] - entry_price) * 100
                pips_close = (p_row["close"] - entry_price) * 100
                pips_open = (p_row["open"] - entry_price) * 100
            else:
                pips_high = (entry_price - p_row["low"]) * 100
                pips_low = (entry_price - p_row["high"]) * 100
                pips_close = (entry_price - p_row["close"]) * 100
                pips_open = (entry_price - p_row["open"]) * 100
                
            # Update tracking metrics (regardless of whether trade is still open)
            if pips_high > running_mfe: running_mfe = pips_high
            if -pips_low > running_mae: running_mae = -pips_low
                
            if minutes_elapsed == 1:
                mfe_1m, mae_1m = running_mfe, running_mae
            if minutes_elapsed == 5:
                mfe_5m, mae_5m = running_mfe, running_mae
                
            if trade_active:
                # CONSERVATIVE PATH ASSUMPTION: 
                # We always evaluate the adverse excursion (Low) before the favorable excursion (High) 
                # within the same M1 bar. This ensures we never artificially survive a spike that 
                # actually stopped us out first.
                
                # 1. Did the adverse excursion hit our current stop?
                if pips_low <= trail_sl:
                    trade_active = False
                    final_pips = trail_sl
                    if trail_sl == -SL_PIPS:
                        hit_sl = True
                        if pips_high >= TRAIL_TRIGGER:
                            intrabar_collision = True # Bar spans both -300 and +500
                    else:
                        trail_survived = True
                        
                # 2. If we survived, did the favorable excursion move our trailing stop?
                if trade_active and pips_high >= TRAIL_TRIGGER:
                    hit_trigger = True
                    new_trail = pips_high - TRAIL_STEP
                    if new_trail > trail_sl:
                        trail_sl = new_trail
                        
                    # 3. Intrabar Retracement Check: Did it spike to High and then retrace 
                    # back down past the NEW trail SL before the bar closed?
                    # Since we don't have ticks, checking the Close is the safest proxy.
                    if pips_close <= trail_sl:
                        trade_active = False
                        final_pips = trail_sl
                        trail_survived = True

        if trade_active and post_news_window.height > 0:
            last_bar = post_news_window.to_dicts()[-1]
            if bias == "BUY":
                final_pips = (last_bar["close"] - entry_price) * 100
            else:
                final_pips = (entry_price - last_bar["close"]) * 100

        print(f"EVENT:              {event_name}")
        print(f"TIMESTAMP:          {event_dt.strftime('%Y-%m-%d %H:%M')}")
        print(f"EVENT_TYPE:         {event_type}")
        print("\nPRE-NEWS FEATURES")
        print(f"forecast:           {forecast}")
        print(f"previous:           {previous}")
        print(f"prior_surprise:     {prior_surprise:+.2f}")
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
        print(f"intrabar_collision: {'YES' if intrabar_collision else 'NO'}")
        print(f"hit_trigger:        {'YES' if hit_trigger else 'NO'}")
        print(f"trail_survival:     {'YES' if trail_survived else 'NO'}")
        print(f"final_pnl:          {final_pips:+.2f} pips")
        print("-" * 50)

if __name__ == "__main__":
    run()
