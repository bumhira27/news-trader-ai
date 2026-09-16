
from pathlib import Path
import polars as pl
from datasets import load_dataset

def clean_value(val):
    if val is None: return None
    if isinstance(val, (int, float)): return float(val)
    val = str(val).strip()
    if not val: return None
    val = val.replace("%", "").replace(",", "")
    multiplier = 1.0
    if val.endswith("K"): val = val[:-1]; multiplier = 1_000.0
    elif val.endswith("M"): val = val[:-1]; multiplier = 1_000_000.0
    elif val.endswith("B"): val = val[:-1]; multiplier = 1_000_000_000.0
    try: return float(val) * multiplier
    except ValueError: return None

def main():
    print("Downloading Ehsanrs2/Forex_Factory_Calendar...")
    dataset = load_dataset("Ehsanrs2/Forex_Factory_Calendar", split="train")
    df = pl.from_arrow(dataset.data.table)
    df = df.rename({c: c.lower() for c in df.columns})

    if "datetime" in df.columns:
        df = df.rename({"datetime": "timestamp"})
        
    df = df.with_columns(
        pl.col("timestamp").str.slice(0, 19).str.to_datetime("%Y-%m-%dT%H:%M:%S", strict=False)
    )

    for col in ["actual", "forecast", "previous"]:
        if col in df.columns:
            df = df.with_columns(pl.col(col).map_elements(clean_value, return_dtype=pl.Float64).alias(col))

    cols = [c for c in ["timestamp", "currency", "event", "impact", "actual", "forecast", "previous"] if c in df.columns]
    df = df.select(cols)
    
    filtered = df.filter(
        (pl.col("timestamp").dt.year() >= 2024)
        & (pl.col("currency") == "USD")
        & (pl.col("impact").str.contains("High"))
        & pl.col("actual").is_not_null()
        & pl.col("forecast").is_not_null()
    )
    
    out_dir = Path(__file__).parent
    filtered_path = out_dir / "calendar_usd_high.parquet"
    filtered.write_parquet(filtered_path)
    print(f"Saved {filtered.height} events to {filtered_path}")

if __name__ == "__main__":
    main()

