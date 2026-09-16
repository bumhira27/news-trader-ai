
import os
import requests
import polars as pl
from pathlib import Path

def main():
    env_path = Path(r"C:\Users\bumhira27\Documents\Machine Learning\.env")
    api_key = None
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("FRED_API_KEY="):
                api_key = line.split("=")[1].strip()

    if not api_key:
        raise ValueError("FRED_API_KEY not found in .env")

    def fetch_series(series_id):
        url = "https://api.stlouisfed.org/fred/series/observations"
        params = {
            "series_id": series_id,
            "api_key": api_key,
            "file_type": "json",
            "observation_start": "2023-10-01",
        }
        res = requests.get(url, params=params)
        res.raise_for_status()
        data = res.json()["observations"]
        
        dates, values = [], []
        for obs in data:
            if obs["value"] != ".":
                dates.append(obs["date"])
                values.append(float(obs["value"]))
        
        df = pl.DataFrame({
            "timestamp": pl.Series(dates).str.to_datetime("%Y-%m-%d"),
            series_id: values
        }).sort("timestamp")
        return df

    print("Fetching FEDFUNDS (Interest Rate)...")
    fedfunds = fetch_series("FEDFUNDS")
    
    print("Fetching DGS10 (10-Year Treasury Yield)...")
    dgs10 = fetch_series("DGS10")

    print("Fetching CPIAUCSL (Inflation Index)...")
    cpi = fetch_series("CPIAUCSL")

    start_date = fedfunds["timestamp"].min()
    end_date = dgs10["timestamp"].max()
    
    daily_df = pl.DataFrame({
        "timestamp": pl.date_range(start_date, end_date, "1d", eager=True).cast(pl.Datetime)
    })
    
    daily_df = daily_df.join_asof(fedfunds, on="timestamp", strategy="backward")
    daily_df = daily_df.join_asof(dgs10, on="timestamp", strategy="backward")
    daily_df = daily_df.join_asof(cpi, on="timestamp", strategy="backward")

    daily_df = daily_df.rename({
        "FEDFUNDS": "fedfunds_rate",
        "DGS10": "us10y_yield",
        "CPIAUCSL": "cpi_index"
    })

    out_path = Path(__file__).parent / "macro_context.parquet"
    daily_df.write_parquet(out_path)
    print(f"Saved macro context to {out_path}")
    print(daily_df.tail(5))

if __name__ == "__main__":
    main()

