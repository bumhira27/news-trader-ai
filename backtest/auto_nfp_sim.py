import sys
from pathlib import Path
import polars as pl
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data.load_prices import load_xauusd_prices

def simulate_m1_trade(entry_price, direction, news_bar, sl_usd, trigger_usd, trail_dist_usd):
    high = news_bar["high"]
    low = news_bar["low"]
    close = news_bar["close"]
    
    if direction == "BUY":
        current_sl = entry_price - sl_usd
        if low <= current_sl: return current_sl - entry_price 
            
        if high >= entry_price + trigger_usd:
            new_sl = high - trail_dist_usd
            if new_sl >= close: return new_sl - entry_price
            else: return close - entry_price
        else: return close - entry_price

    else: 
        current_sl = entry_price + sl_usd
        if high >= current_sl: return entry_price - current_sl
            
        if low <= entry_price - trigger_usd:
            new_sl = low + trail_dist_usd
            if new_sl <= close: return entry_price - new_sl
            else: return entry_price - close
        else: return entry_price - close


def main():
    prices = load_xauusd_prices([
        r"C:\Users\bumhira27\Downloads\XAUUSD_2024_all.csv",
        r"C:\Users\bumhira27\Downloads\XAUUSD_2025_all.csv",
        r"C:\Users\bumhira27\Downloads\XAUUSD_2026\*.csv"
    ])
    
    # We will automatically detect the true NFP bar for every single month from Jan 2024 to Aug 2026.
    # NFP is always on a Friday, between 14:30 and 15:30 broker time, and causes the biggest spike.
    
    # Add year, month, weekday columns
    df = prices.with_columns([
        pl.col("timestamp").dt.year().alias("year"),
        pl.col("timestamp").dt.month().alias("month"),
        pl.col("timestamp").dt.weekday().alias("weekday"),
        pl.col("timestamp").dt.hour().alias("hour"),
        pl.col("timestamp").dt.minute().alias("minute"),
        (pl.col("high") - pl.col("low")).alias("range")
    ])
    
    # Filter for Fridays (5) in the first 14 days of the month, between 14:00 and 16:00
    fridays = df.filter(
        (pl.col("weekday") == 5) & 
        (pl.col("timestamp").dt.day() <= 14) & 
        (pl.col("hour") >= 14) & (pl.col("hour") <= 15)
    )
    
    # For each year and month, find the 1-minute bar with the absolute maximum range
    nfp_bars = fridays.sort("range", descending=True).group_by(["year", "month"]).first().sort(["year", "month"])
    
    trades = []
    
    # Pre-release directional bias logic (mocked for backtest - in real life we fetch the forecast)
    # We will assume a perfect entry just to test the raw M1 scalping mechanics of the user's trailing stop.
    
    print("\n=== TRUE NFP M1 CANDLES (2024 - 2026) ===")
    print(f"{'Date':<18} | {'Entry':<8} | {'High':<8} | {'Low':<8} | {'Close':<8} | {'Range(pips)':<10}")
    print("-" * 75)
    
    for row in nfp_bars.to_dicts():
        news_time = row["timestamp"]
        
        # Get entry price (close of the minute before)
        entry_bar = prices.filter(pl.col("timestamp") < news_time).tail(1)
        if entry_bar.height == 0: continue
        entry_price = entry_bar["close"][0]
        
        # Determine bias retroactively to see if the trailing logic survives the whip
        direction = "BUY" if row["close"] > entry_price else "SELL"
        
        trades.append({
            "time": news_time,
            "bias": direction,
            "entry": entry_price,
            "bar": row
        })
        
        rng = round(row['range'] * 100)
        print(f"{str(news_time)[:16]:<18} | {entry_price:<8.2f} | {row['high']:<8.2f} | {row['low']:<8.2f} | {row['close']:<8.2f} | {rng:<10}")

    print(f"\nTotal NFP Events Found: {len(trades)}")
    
    # Run user's Setup B
    s = {"name": "Setup B (SL 250 | Trig 500 | Trail 200)", "sl": 2.5, "trig": 5.0, "trail": 2.0}
    
    print(f"\n--- {s['name']} ---")
    print(f"{'Date':<18} | {'PnL Pips':<8} | {'Note':<8}")
    print("-" * 45)
    
    total_pips = 0
    wins = 0
    losses = 0
    
    for t in trades:
        pnl_usd = simulate_m1_trade(t['entry'], t['bias'], t['bar'], s['sl'], s['trig'], s['trail'])
        pips = round(pnl_usd * 100)
        total_pips += pips
        if pips > 0: 
            wins += 1
            note = "WIN"
        else: 
            losses += 1
            note = "LOSS"
        print(f"{str(t['time'])[:16]:<18} | {pips:<8} | {note:<8}")
        
    print("-" * 45)
    print(f"Total Net Pips (2024 - 2026/08): {total_pips} ({wins} W / {losses} L)")

if __name__ == "__main__":
    main()
