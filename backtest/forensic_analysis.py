import sys
from pathlib import Path
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data.load_prices import load_xauusd_prices
from scoring.multi_factor_scorecard import MacroScorecard

def main():
    project_root = Path(__file__).resolve().parent.parent
    calendar = pl.read_parquet(project_root / "data" / "calendar_usd_high.parquet")
    if "datetime" in calendar.columns: calendar = calendar.rename({"datetime": "timestamp"})
    macro = pl.read_parquet(project_root / "data" / "macro_context.parquet")
    
    prices = load_xauusd_prices([
        r"C:\Users\bumhira27\Downloads\XAUUSD_2024_all.csv",
        r"C:\Users\bumhira27\Downloads\XAUUSD_2025_all.csv",
        r"C:\Users\bumhira27\Downloads\XAUUSD_2026\*.csv"
    ])
    prices = prices.with_columns([
        (pl.col("high") - pl.col("low")).alias("range"),
        pl.col("timestamp").dt.date().alias("date")
    ])
    
    events = calendar.sort("timestamp").join_asof(macro.sort("timestamp"), on="timestamp", strategy="backward")
    scorecard = MacroScorecard()
    
    target_events = ["Non-Farm Employment Change", "CPI m/m", "Core CPI m/m"]
    forensic_data = []
    
    for row in events.to_dicts():
        d = row["timestamp"].date()
        if d.year < 2024: continue
        event_name = row.get("event", "")
        if event_name not in target_events: continue
        
        forecast = row.get("forecast")
        previous = row.get("previous")
        actual = row.get("actual")
        
        if forecast is None or previous is None: continue
            
        window = prices.filter((pl.col("date") == d) & (pl.col("timestamp").dt.hour() >= 13) & (pl.col("timestamp").dt.hour() <= 18))
        if window.height == 0: continue
        
        news_bar_row = window.sort("range", descending=True).head(1).to_dicts()[0]
        news_time = news_bar_row["timestamp"]
        entry_bar = prices.filter(pl.col("timestamp") < news_time).tail(1)
        if entry_bar.height == 0: continue
        
        entry_price = entry_bar["close"][0]
        real_bias = "BUY" if news_bar_row["close"] > entry_price else "SELL"
        rng_pips = round(news_bar_row["range"] * 100)
        
        kwargs = {
            "current_rate": row.get("fedfunds_rate", 5.33),
            "us10y_yield": row.get("us10y_yield", 4.2),
        }
        
        if "CPI" in event_name:
            kwargs["cpi_forecast"] = forecast
            kwargs["cpi_previous"] = previous
        else:
            kwargs["nfp_forecast"] = forecast
            kwargs["nfp_previous"] = previous
            
        result = scorecard.generate_pre_release_scorecard(**kwargs)
        pred_bias = result["bias"]
        
        if pred_bias == "SKIP": continue
            
        is_accurate = "Y" if pred_bias == real_bias else "N"
        
        surprise_val = 0.0
        if actual is not None:
            surprise_val = actual - forecast
            
        forensic_data.append({
            "Date": str(d),
            "Event": "NFP" if "Farm" in event_name else "CPI",
            "Prev": previous,
            "Fcst": forecast,
            "Act": actual if actual is not None else 0.0,
            "Pred": pred_bias,
            "Real": real_bias,
            "Acc": is_accurate,
            "Range": rng_pips,
            "Fcst_Delta": round(forecast - previous, 2),
            "Surprise": round(surprise_val, 2)
        })
        
    print("\n=== FORENSIC ANALYSIS: FORECAST vs ACTUAL IMPACT ===")
    print(f"{'Date':<12} | {'Event':<4} | {'Prev':<6} | {'Fcst':<6} | {'Act':<6} | {'Pred':<5} | {'Real':<5} | {'Acc':<3} | {'Range':<6} | {'F-Delta':<8} | {'Surprise'}")
    print("-" * 95)
    
    flat_ranges = []
    agg_ranges = []
    
    # Sort to keep NFP and CPI grouped logically
    forensic_data.sort(key=lambda x: (x["Event"], x["Date"]))
    
    for f in forensic_data:
        print(f"{f['Date']:<12} | {f['Event']:<4} | {f['Prev']:<6} | {f['Fcst']:<6} | {f['Act']:<6} | {f['Pred']:<5} | {f['Real']:<5} | {f['Acc']:<3} | {f['Range']:<6} | {f['Fcst_Delta']:<8} | {f['Surprise']}")
        
        if abs(f['Fcst_Delta']) < 0.01:
            flat_ranges.append(f['Range'])
        else:
            agg_ranges.append(f['Range'])
            
    print("\n--- VOLATILITY IMPACT ANALYSIS ---")
    if flat_ranges:
        print(f"Avg Range when Forecast == Previous (No change expected): {sum(flat_ranges)/len(flat_ranges):.0f} pips")
    if agg_ranges:
        print(f"Avg Range when Forecast != Previous (Change expected):    {sum(agg_ranges)/len(agg_ranges):.0f} pips")
        
    print("\n--- ACCURACY DIAGNOSTIC ---")
    accurate = [f for f in forensic_data if f['Acc'] == 'Y']
    inaccurate = [f for f in forensic_data if f['Acc'] == 'N']
    
    acc_surprise_avg = sum([abs(f['Surprise']) for f in accurate]) / max(len(accurate), 1)
    inacc_surprise_avg = sum([abs(f['Surprise']) for f in inaccurate]) / max(len(inaccurate), 1)
    
    print(f"When Prediction is CORRECT (Y), avg Actual deviation from Forecast (Surprise) is: {acc_surprise_avg:.2f}")
    print(f"When Prediction is WRONG (N), avg Actual deviation from Forecast (Surprise) is:   {inacc_surprise_avg:.2f}")
    print(f"\nConclusion: A higher 'Surprise' metric forces the market to move against the pre-release 'Pred' bias.")

if __name__ == "__main__":
    main()
