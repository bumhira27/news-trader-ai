
import polars as pl
from pathlib import Path
import glob
from datetime import datetime
import datetime as dt

def load_xauusd_prices(paths: list[str | Path]) -> pl.DataFrame:
    dfs = []
    columns = ["date", "time", "open", "high", "low", "close", "volume"]
    for path in paths:
        path = str(path)
        files = glob.glob(path) if "*" in path else [path]
        for f in files:
            print(f"    Loading {f}...")
            # Files have no header, format is Date, Time, Open, High, Low, Close, Volume
            df = pl.read_csv(f, has_header=False, new_columns=columns)
            
            df = df.with_columns(
                (pl.col("date").cast(pl.String) + " " + pl.col("time").cast(pl.String))
                .str.to_datetime("%Y.%m.%d %H:%M", strict=False).alias("timestamp")
            )
            
            cols = ["timestamp", "open", "high", "low", "close", "volume"]
            dfs.append(df.select(cols))
            
    if not dfs:
        raise ValueError("No price data found.")
        
    combined = pl.concat(dfs).sort("timestamp").unique("timestamp")
    return combined

def measure_post_event_move(prices: pl.DataFrame, event_time: datetime, direction: str, windows_minutes: list[int] = [5, 15, 30, 60]) -> dict:
    result = {}
    entry_candidates = prices.filter(pl.col("timestamp") <= event_time).sort("timestamp", descending=True)
    if entry_candidates.height == 0:
        return result
    
    entry_price = entry_candidates.get_column("close")[0]
    
    for minutes in windows_minutes:
        end_time = event_time + dt.timedelta(minutes=minutes)
        window_df = prices.filter(
            (pl.col("timestamp") > event_time) & (pl.col("timestamp") <= end_time)
        )
        
        if window_df.height == 0:
            result[f"mfe_{minutes}m"] = None
            result[f"mae_{minutes}m"] = None
            continue
            
        max_high = window_df.get_column("high").max()
        min_low = window_df.get_column("low").min()
        
        if direction.lower() == "buy":
            mfe = max_high - entry_price
            mae = entry_price - min_low
        elif direction.lower() == "sell":
            mfe = entry_price - min_low
            mae = max_high - entry_price
        else:
            mfe, mae = None, None
            
        result[f"mfe_{minutes}m"] = mfe
        result[f"mae_{minutes}m"] = mae
        
    return result

