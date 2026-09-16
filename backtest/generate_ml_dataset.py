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

# We will analyze our 46 Holy Trinity trades
TRINITY_TRADES = [
    ("2024-01-05 15:30", "NFP",          "SELL"),
    ("2024-01-11 15:30", "CPI",          "SELL"),
    ("2024-01-17 15:30", "Retail Sales", "SELL"),
    ("2024-02-02 15:30", "NFP",          "BUY"),
    ("2024-02-13 15:30", "CPI",          "SELL"),
    ("2024-02-15 15:30", "Retail Sales", "SELL"),
    ("2024-03-08 15:30", "NFP",          "BUY"),
    ("2024-03-12 15:32", "CPI",          "BUY"),
    ("2024-03-14 15:30", "Retail Sales", "BUY"),
    ("2024-04-05 15:30", "NFP",          "BUY"),
    ("2024-04-10 15:30", "CPI",          "SELL"),
    ("2024-04-15 17:06", "Retail Sales", "BUY"),
    ("2024-05-03 15:30", "NFP",          "SELL"),
    ("2024-05-15 15:30", "CPI",          "BUY"),
    ("2024-05-15 15:30", "Retail Sales", "BUY"),
    ("2024-06-07 15:30", "NFP",          "BUY"),
    ("2024-06-12 15:30", "CPI",          "BUY"),
    ("2024-06-18 15:30", "Retail Sales", "SELL"),
    ("2024-07-05 15:30", "NFP",          "BUY"),
    ("2024-07-11 15:30", "CPI",          "BUY"),
    ("2024-07-16 15:30", "Retail Sales", "SELL"),
    ("2024-08-02 15:30", "NFP",          "BUY"),
    ("2024-08-14 15:30", "CPI",          "BUY"),
    ("2024-08-15 16:00", "Retail Sales", "SELL"),
    ("2024-09-06 15:30", "NFP",          "SELL"),
    ("2024-09-11 15:30", "CPI",          "BUY"),
    ("2024-09-17 15:30", "Retail Sales", "SELL"),
    ("2024-10-04 15:30", "NFP",          "SELL"),
    ("2024-10-10 15:30", "CPI",          "BUY"),
    ("2024-10-17 15:30", "Retail Sales", "BUY"),
    ("2024-11-01 15:30", "NFP",          "SELL"),
    ("2024-11-13 15:30", "CPI",          "BUY"),
    ("2024-11-15 15:30", "Retail Sales", "SELL"),
    ("2024-12-06 15:30", "NFP",          "BUY"),
    ("2024-12-11 15:30", "CPI",          "SELL"),
    ("2024-12-17 15:30", "Retail Sales", "BUY"),
    ("2025-01-10 15:30", "NFP",          "BUY"),
    ("2025-01-15 15:30", "CPI",          "SELL"),
    ("2025-01-16 15:30", "Retail Sales", "BUY"),
    ("2025-02-07 15:30", "NFP",          "BUY"),
    ("2025-02-12 15:30", "CPI",          "SELL"),
    ("2025-02-14 17:34", "Retail Sales", "BUY"),
    ("2025-03-07 15:30", "NFP",          "SELL"),
    ("2025-03-12 15:30", "CPI",          "BUY"),
    ("2025-03-17 15:48", "Retail Sales", "SELL"),
    ("2025-04-04 14:45", "NFP",          "SELL"),
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
    
    # Match the event by Date (Year, Month, Day) since calendar times might not align perfectly
    events_in_window = cal_df.filter(
        (pl.col("timestamp").dt.year() == target_dt.year) & 
        (pl.col("timestamp").dt.month() == target_dt.month) &
        (pl.col("timestamp").dt.day() == target_dt.day)
    )
    
    # Filter by event_type keyword
    if event_type == "NFP":
        keyword = "Non-Farm"
    elif event_type == "CPI":
        keyword = "CPI"
    elif event_type == "Retail Sales":
        keyword = "Retail Sales"
    else:
        keyword = event_type
        
    matched = events_in_window.filter(
        pl.col("event").str.to_lowercase().str.contains(keyword.lower())
    )
    
    if matched.height == 0:
        return {}
        
    row = matched.to_dicts()[0]
    
    # Find prior surprise (we need the previous release of the SAME event)
    historical = cal_df.filter(
        (pl.col("event") == row["event"]) & 
        (pl.col("timestamp") < target_dt)
    ).sort("timestamp", descending=True)
    
    prior_surprise = 0.0
    if historical.height > 0:
        prev_row = historical.to_dicts()[0]
        if prev_row["actual"] is not None and prev_row["forecast"] is not None:
            prior_surprise = prev_row["actual"] - prev_row["forecast"]
            
    # Calculate current surprise
    surprise = 0.0
    if row["actual"] is not None and row["forecast"] is not None:
        surprise = row["actual"] - row["forecast"]
        
    return {
        "event_name": row["event"],
        "actual": row["actual"],
        "forecast": row["forecast"],
        "previous": row["previous"],
        "surprise": surprise,
        "prior_surprise": prior_surprise
    }

def calculate_atr(df: pl.DataFrame, periods: int = 14) -> float:
    if df.height < periods:
        return 0.0
    
    # TR = max(H-L, abs(H-Cp), abs(L-Cp))
    df = df.with_columns([
        pl.col("close").shift(1).alias("prev_close")
    ]).fill_null(strategy="backward")
    
    df = df.with_columns([
        (pl.col("high") - pl.col("low")).alias("tr1"),
        (pl.col("high") - pl.col("prev_close")).abs().alias("tr2"),
        (pl.col("low") - pl.col("prev_close")).abs().alias("tr3"),
    ])
    
    df = df.with_columns([
        pl.max_horizontal(["tr1", "tr2", "tr3"]).alias("tr")
    ])
    
    return df["tr"].tail(periods).mean() * 100 # convert to pips

def run():
    print("Loading price data (this may take a moment)...")
    prices = load_xauusd_prices(PRICE_PATHS)
    cal_df = load_calendar()

    print("\nGenerating ML Dataset Format for News Trades...\n")

    for dt_str, event_type, bias in TRINITY_TRADES:
        event_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
        
        # Get Calendar features
        cal_features = get_event_data(cal_df, event_dt, event_type)
        if not cal_features:
            # Fallback if no calendar data found
            cal_features = {
                "event_name": f"{event_type} (From System)",
                "actual": 0.0, "forecast": 0.0, "previous": 0.0,
                "surprise": 0.0, "prior_surprise": 0.0
            }
            
        # Get Pre-news Price features (15 mins prior)
        ts = pl.col("timestamp")
        pre_news_window = prices.filter(
            (ts >= event_dt - timedelta(minutes=15)) & 
            (ts < event_dt)
        )
        
        if pre_news_window.height == 0:
            continue
            
        entry_price = pre_news_window["close"][-1]
        pre_range_high = pre_news_window["high"].max()
        pre_range_low = pre_news_window["low"].min()
        pre_news_range = (pre_range_high - pre_range_low) * 100
        
        pre_open = pre_news_window["open"][0]
        pre_news_trend = "Bullish" if entry_price >= pre_open else "Bearish"
        
        volatility = calculate_atr(pre_news_window, 14)
        
        # Get Post-news Outcomes (10 mins after)
        post_news_window = prices.filter(
            (ts >= event_dt) & 
            (ts <= event_dt + timedelta(minutes=10))
        )
        
        if post_news_window.height == 0:
            continue
            
        post_high = post_news_window["high"].max()
        post_low = post_news_window["low"].min()
        
        if bias == "BUY":
            mfe = (post_high - entry_price) * 100
            mae = (entry_price - post_low) * 100
        else:
            mfe = (entry_price - post_low) * 100
            mae = (post_high - entry_price) * 100
            
        # Strategy Logic Application
        hit_300_sl = mae >= SL_PIPS
        hit_500_trigger = mfe >= TRAIL_TRIGGER
        
        # PnL logic (same as backtester)
        if hit_300_sl:
            final_pips = -SL_PIPS
            trail_survived = False
        elif hit_500_trigger:
            final_pips = mfe - TRAIL_STEP
            trail_survived = True
        else:
            spike_bar = post_news_window.sort("high", descending=True).head(1).to_dicts()[0]
            if bias == "BUY":
                final_pips = (spike_bar["close"] - entry_price) * 100
            else:
                final_pips = (entry_price - spike_bar["close"]) * 100
            trail_survived = False
            
        # PnL value assuming 1.0 standard lot ($1 per pip on XAUUSD per 100oz)
        final_pnl_usd = final_pips * 1.0  
        
        # ─── PRINT FORMAT AS REQUESTED ───
        print(f"EVENT: {cal_features['event_name']}")
        print(f"TIMESTAMP: {dt_str}")
        print("\nINPUTS")
        print(f"Actual:             {cal_features['actual']}")
        print(f"Forecast:           {cal_features['forecast']}")
        print(f"Surprise:           {cal_features['surprise']:+.2f}")
        print(f"Previous:           {cal_features['previous']}")
        print(f"Prior Surprise:     {cal_features['prior_surprise']:+.2f}")
        print(f"XAU Pre:            {entry_price:.2f}")
        print(f"Pre-news range:     {pre_news_range:.1f}")
        print(f"Pre-news trend:     {pre_news_trend}")
        print(f"Spread:             0.25 (Simulated)")
        print(f"Volatility:         {volatility:.1f}")
        
        print("\nMODEL")
        print(f"Prediction:         {bias}")
        print(f"Confidence:         N/A (Heuristic)")
        
        print("\nOUTCOME")
        print(f"MFE:                {mfe:+.1f}")
        print(f"MAE:                {-mae:+.1f}")
        print(f"Hit 300 SL:         {'YES' if hit_300_sl else 'NO'}")
        print(f"Hit 500 trigger:    {'YES' if hit_500_trigger else 'NO'}")
        print(f"Trail survived:     {'YES' if trail_survived else 'NO'}")
        print(f"Final P&L:          {final_pnl_usd:+.2f} pips")
        print("-" * 50)
        
if __name__ == "__main__":
    run()
