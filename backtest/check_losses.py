import sys
from pathlib import Path
import polars as pl
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data.load_prices import load_xauusd_prices

def main():
    prices = load_xauusd_prices([
        r"C:\Users\bumhira27\Downloads\XAUUSD_2024_all.csv",
        r"C:\Users\bumhira27\Downloads\XAUUSD_2025_all.csv",
        r"C:\Users\bumhira27\Downloads\XAUUSD_2026\*.csv"
    ])
    prices = prices.with_columns(pl.col("timestamp").dt.date().alias("date"))

    targets = [
        ("NFP", "2024-09-06", 15, 30),
        ("NFP", "2025-02-07", 15, 30),
        ("ISM", "2024-10-01", 17, 0),
        ("CPI", "2024-09-11", 15, 30),
        ("FOMC", "2024-05-01", 21, 0)
    ]

    print("\n=== FORENSIC OHLC ANALYSIS OF LOSSES ===")
    for event, date_str, hr, mn in targets:
        # Filter for the specific date and hour
        # Let's grab the minute before the news (entry) and the news minute itself
        window = prices.filter(
            (pl.col("date").cast(pl.Utf8) == date_str) & 
            (pl.col("timestamp").dt.hour() == hr) & 
            (pl.col("timestamp").dt.minute() >= mn - 2) &
            (pl.col("timestamp").dt.minute() <= mn + 1)
        ).sort("timestamp").to_dicts()
        
        print(f"\n--- {event} {date_str} ---")
        for w in window:
            rng = round((w['high'] - w['low']) * 100)
            print(f"{w['timestamp'].strftime('%H:%M:00')} | O: {w['open']:.2f} | H: {w['high']:.2f} | L: {w['low']:.2f} | C: {w['close']:.2f} | Range: {rng} pips")

if __name__ == "__main__":
    main()
