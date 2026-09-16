import sys
from pathlib import Path
import polars as pl
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data.load_prices import load_xauusd_prices
from scoring.multi_factor_scorecard import MacroScorecard

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

def get_event_dates(df_cal, event_names):
    dates = df_cal.filter(pl.col("event").is_in(event_names))["timestamp"].dt.date().unique().to_list()
    return sorted(dates)

def main():
    project_root = Path(__file__).resolve().parent.parent
    
    # 1. Load Data
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
    
    # 2. Get predictions via Macro Scorecard
    events = calendar.sort("timestamp").join_asof(macro.sort("timestamp"), on="timestamp", strategy="backward")
    
    scorecard = MacroScorecard()
    rows = events.to_dicts()
    valid_predictions = []
    
    for row in rows:
        forecast = row.get("forecast")
        previous = row.get("previous")
        event_name = row.get("event", "").lower()
        
        kwargs = {
            "current_rate": row.get("fedfunds_rate", 5.33),
            "us10y_yield": row.get("us10y_yield", 4.2),
        }
        
        if forecast is not None and previous is not None:
            if "cpi" in event_name or "pce" in event_name:
                kwargs["cpi_forecast"] = forecast
                kwargs["cpi_previous"] = previous
            elif "non-farm" in event_name:
                kwargs["nfp_forecast"] = forecast
                kwargs["nfp_previous"] = previous
            elif "claims" in event_name:
                kwargs["claims_forecast"] = forecast
                kwargs["claims_previous"] = previous
            elif "ism" in event_name or "retail" in event_name:
                kwargs["growth_forecast"] = forecast
                kwargs["growth_previous"] = previous
            elif "federal funds" in event_name or "fomc" in event_name:
                kwargs["expected_rate"] = forecast
                
        result = scorecard.generate_pre_release_scorecard(**kwargs)
        if result["bias"] != "SKIP" and abs(result["total_score"]) > 0.0:
            valid_predictions.append({
                "date": row["timestamp"].date(),
                "event": row["event"],
                "bias": result["bias"],
                "score": result["total_score"]
            })
            
    pred_df = pl.DataFrame(valid_predictions)
    if pred_df.height == 0:
        print("No valid predictions found.")
        return

    # 3. User Settings
    settings = {
        "NFP": {"sl": 2.5, "trig": 2.0, "trail": 1.0},
        "CPI": {"sl": 2.5, "trig": 2.0, "trail": 1.0},
        "Retail Sales": {"sl": 2.0, "trig": 2.0, "trail": 1.0},
        "ISM": {"sl": 2.5, "trig": 2.0, "trail": 1.0},
        "FOMC": {"sl": 3.0, "trig": 2.0, "trail": 1.0},
        "PCE": {"sl": 2.5, "trig": 2.0, "trail": 1.0}
    }
    
    event_groups = {
        "NFP": ["Non-Farm Employment Change"],
        "CPI": ["CPI m/m", "Core CPI m/m", "CPI y/y"],
        "Retail Sales": ["Retail Sales m/m", "Core Retail Sales m/m"],
        "ISM": ["ISM Manufacturing PMI", "ISM Services PMI"],
        "FOMC": ["Federal Funds Rate"],
        "PCE": ["Core PCE Price Index m/m"]
    }
    
    results = []
    
    # 4. Simulate Trades
    for group_name, event_names in event_groups.items():
        dates = get_event_dates(calendar, event_names)
        
        for d in dates:
            if d.year < 2024: continue
            
            group_preds = pred_df.filter((pl.col("date") == d) & (pl.col("event").is_in(event_names)))
            if group_preds.height == 0: continue
            
            bias = group_preds["bias"][0]
            
            # Find the true spike based on correct broker time
            if group_name == "FOMC":
                window = prices.filter((pl.col("date") == d) & (pl.col("timestamp").dt.hour() >= 19))
            else:
                window = prices.filter((pl.col("date") == d) & (pl.col("timestamp").dt.hour() >= 13) & (pl.col("timestamp").dt.hour() <= 18))
                
            if window.height == 0: continue
            
            news_bar_row = window.sort("range", descending=True).head(1).to_dicts()[0]
            news_time = news_bar_row["timestamp"]
            
            entry_bar = prices.filter(pl.col("timestamp") < news_time).tail(1)
            if entry_bar.height == 0: continue
            entry_price = entry_bar["close"][0]
            
            s = settings[group_name]
            pnl_usd = simulate_m1_trade(entry_price, bias, news_bar_row, s["sl"], s["trig"], s["trail"])
            pips = round(pnl_usd * 100)
            rng_pips = round(news_bar_row["range"] * 100)
            
            results.append({
                "Group": group_name,
                "Date": news_time,
                "Bias": bias,
                "Range": rng_pips,
                "PnL": pips,
                "Note": "WIN" if pips > 0 else "LOSS"
            })
            
    # 5. Print Output
    print("\n=== MACRO PREDICTIVE M1 BACKTEST (REAL DIRECTIONAL BIAS) ===")
    
    grand_total_pips = 0
    grand_wins = 0
    grand_losses = 0
    
    for group in event_groups.keys():
        group_results = [r for r in results if r["Group"] == group]
        if not group_results: continue
        
        s = settings[group]
        print(f"\n--- {group.upper()} (SL {int(s['sl']*100)} | Trig {int(s['trig']*100)} | Trail {int(s['trail']*100)}) ---")
        print(f"{'Date Time':<18} | {'Bias':<5} | {'Range(pips)':<12} | {'PnL Pips':<10} | {'Result':<8}")
        print("-" * 65)
        
        grp_pips = 0
        grp_wins = 0
        grp_losses = 0
        
        for r in group_results:
            print(f"{str(r['Date'])[:16]:<18} | {r['Bias']:<5} | {r['Range']:<12} | {r['PnL']:<10} | {r['Note']:<8}")
            grp_pips += r["PnL"]
            if r["PnL"] > 0: grp_wins += 1
            else: grp_losses += 1
            
        print("-" * 65)
        print(f"{group} Total: {grp_pips} Pips ({grp_wins} W / {grp_losses} L)")
        
        grand_total_pips += grp_pips
        grand_wins += grp_wins
        grand_losses += grp_losses
        
    print("\n" + "="*65)
    print(f"PREDICTIVE GRAND TOTAL: {grand_total_pips} Pips ({grand_wins} W / {grand_losses} L)")
    print("="*65 + "\n")

if __name__ == "__main__":
    main()
