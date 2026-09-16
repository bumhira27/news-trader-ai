import sys
from pathlib import Path
import polars as pl
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data.load_prices import load_xauusd_prices

def main():
    prices = load_xauusd_prices([r"C:\Users\bumhira27\Downloads\XAUUSD_2024_all.csv"])
    
    target_time = datetime(2024, 1, 31, 16, 45)
    
    window = prices.filter(
        (pl.col("timestamp") >= target_time - pl.duration(minutes=1)) & 
        (pl.col("timestamp") <= target_time + pl.duration(minutes=30))
    )
    
    print("--- RAW 1-MIN BARS ---")
    for row in window.iter_rows(named=True):
        print(f"{row['timestamp']} | O: {row['open']} | H: {row['high']} | L: {row['low']} | C: {row['close']}")
        
if __name__ == "__main__":
    main()
