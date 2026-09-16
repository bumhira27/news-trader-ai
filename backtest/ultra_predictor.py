import sys
from pathlib import Path
import polars as pl
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data.load_prices import load_xauusd_prices

def get_latest(calendar, event_name, before_time, days=30):
    start = before_time - timedelta(days=days)
    res = calendar.filter((pl.col("event") == event_name) & (pl.col("timestamp") < before_time) & (pl.col("timestamp") >= start))
    if res.height > 0: return res.sort("timestamp", descending=True).to_dicts()[0]
    return None

def calc_score(row, inverse=False):
    if not row or row["actual"] is None or row["forecast"] is None: return 0
    if row["actual"] > row["forecast"]: return 1 if inverse else -1
    if row["actual"] < row["forecast"]: return -1 if inverse else 1
    return 0

def get_leading_score(event_name, news_time, calendar):
    if "Farm" in event_name:
        adp = get_latest(calendar, "ADP Non-Farm Employment Change", news_time, 7)
        claims = get_latest(calendar, "Unemployment Claims", news_time, 7)
        score = calc_score(adp)*1.5 + calc_score(claims, True)*1.0
        return 1 if score >= 1 else (-1 if score <= -1 else 0)
    if "CPI" in event_name:
        wages = get_latest(calendar, "Average Hourly Earnings m/m", news_time, 14)
        ism_mfg = get_latest(calendar, "ISM Manufacturing PMI", news_time, 14)
        score = calc_score(wages)*1.5 + calc_score(ism_mfg)*1.0
        return 1 if score >= 1 else (-1 if score <= -1 else 0)
    if "Retail" in event_name:
        conf = get_latest(calendar, "CB Consumer Confidence", news_time, 30)
        score = calc_score(conf) * 2.0
        return 1 if score >= 1 else (-1 if score <= -1 else 0)
    if "ISM" in event_name:
        empire = get_latest(calendar, "Empire State Manufacturing Index", news_time, 20)
        score = calc_score(empire) * 2.0
        return 1 if score >= 1 else (-1 if score <= -1 else 0)
    return 0

def get_forecast_bias(event_name, news_time, calendar):
    row = get_latest(calendar, event_name, news_time + timedelta(minutes=1), 1)
    if not row or row["forecast"] is None or row["previous"] is None: return 0
    if row["forecast"] > row["previous"]:
        return 1 if "Unemployment" in event_name or "Claims" in event_name else -1
    elif row["forecast"] < row["previous"]:
        return -1 if "Unemployment" in event_name or "Claims" in event_name else 1
    return 0

def main():
    project_root = Path(__file__).resolve().parent.parent
    calendar = pl.read_parquet(project_root / "data" / "calendar_usd_high.parquet")
    if "datetime" in calendar.columns: calendar = calendar.rename({"datetime": "timestamp"})
    
    prices = load_xauusd_prices([
        r"C:\Users\bumhira27\Downloads\XAUUSD_2024_all.csv",
        r"C:\Users\bumhira27\Downloads\XAUUSD_2025_all.csv",
        r"C:\Users\bumhira27\Downloads\XAUUSD_2026\*.csv"
    ])
    prices = prices.with_columns([
        (pl.col("high") - pl.col("low")).alias("range"),
        pl.col("timestamp").dt.date().alias("date")
    ])
    
    events_to_test = {
        "NFP": ["Non-Farm Employment Change"],
        "CPI": ["CPI m/m", "Core CPI m/m"],
        "Retail Sales": ["Retail Sales m/m"],
        "ISM": ["ISM Manufacturing PMI", "ISM Services PMI"],
        "FOMC": ["Federal Funds Rate"],
        "PCE": ["Core PCE Price Index m/m"]
    }
    
    dataset = []
    
    for group_name, event_names in events_to_test.items():
        dates = calendar.filter(pl.col("event").is_in(event_names))["timestamp"].dt.date().unique().to_list()
        for d in sorted(dates):
            if d.year < 2024: continue
            
            hr_min = 13
            hr_max = 18
            if group_name == "FOMC":
                hr_min = 19
                hr_max = 23
                
            window = prices.filter((pl.col("date") == d) & (pl.col("timestamp").dt.hour() >= hr_min) & (pl.col("timestamp").dt.hour() <= hr_max))
            if window.height == 0: continue
            
            news_bar = window.sort("range", descending=True).head(1).to_dicts()[0]
            news_time = news_bar["timestamp"]
            
            entry_bar = prices.filter(pl.col("timestamp") < news_time).tail(1)
            bar_15m = prices.filter(pl.col("timestamp") <= news_time - timedelta(minutes=15)).tail(1)
            bar_1h = prices.filter(pl.col("timestamp") <= news_time - timedelta(hours=1)).tail(1)
            bar_4h = prices.filter(pl.col("timestamp") <= news_time - timedelta(hours=4)).tail(1)
            
            if entry_bar.height == 0 or bar_1h.height == 0 or bar_4h.height == 0: continue
                
            entry_price = entry_bar["close"][0]
            price_15m = bar_15m["close"][0]
            price_1h = bar_1h["close"][0]
            price_4h = bar_4h["close"][0]
            
            real_bias = 1 if news_bar["close"] > entry_price else -1
            trend_15m = 1 if entry_price > price_15m else -1
            trend_1h = 1 if entry_price > price_1h else -1
            trend_4h = 1 if entry_price > price_4h else -1
            fcst_bias = get_forecast_bias(event_names[0], news_time, calendar)
            lead_score = get_leading_score(event_names[0], news_time, calendar)
            
            dataset.append({
                "Group": group_name,
                "Date": news_time,
                "RealBias": real_bias,
                "Trend_15m": trend_15m,
                "Trend_1h": trend_1h,
                "Trend_4h": trend_4h,
                "Forecast": fcst_bias,
                "Leading": lead_score
            })
            
    print("\n=== ULTRA-STRICT CONFLUENCE OPTIMIZER (>80% TARGET) ===")
    
    models = {
        "M10: Triple Confluence (Forecast + Lead + 1H Trend)": lambda r: r["Forecast"] if (r["Forecast"] == r["Leading"] == r["Trend_1h"] and r["Forecast"] != 0) else 0,
        "M11: Pure Trend (15m + 1H + 4H all agree)": lambda r: r["Trend_15m"] if (r["Trend_15m"] == r["Trend_1h"] == r["Trend_4h"]) else 0,
        "M12: Pure Mean Reversion (15m + 1H + 4H agree -> INVERSE)": lambda r: -r["Trend_15m"] if (r["Trend_15m"] == r["Trend_1h"] == r["Trend_4h"]) else 0,
        "M13: Leading + 1H Trend Match": lambda r: r["Leading"] if (r["Leading"] == r["Trend_1h"] and r["Leading"] != 0) else 0,
        "M14: Forecast + 4H Trend Match": lambda r: r["Forecast"] if (r["Forecast"] == r["Trend_4h"] and r["Forecast"] != 0) else 0,
        "M15: Inverse Forecast + 15m Trend Match": lambda r: -r["Forecast"] if (-r["Forecast"] == r["Trend_15m"] and r["Forecast"] != 0) else 0,
        "M16: Leading + Forecast Match": lambda r: r["Leading"] if (r["Leading"] == r["Forecast"] and r["Leading"] != 0) else 0,
        "M17: Forecast + 15m Trend Match": lambda r: r["Forecast"] if (r["Forecast"] == r["Trend_15m"] and r["Forecast"] != 0) else 0,
    }
    
    for group in events_to_test.keys():
        group_data = [d for d in dataset if d["Group"] == group]
        if not group_data: continue
        
        print(f"\n--- Optimizing {group} ---")
        best_model_name = ""
        best_win_rate = 0.0
        
        results_for_group = []
        
        for name, model_func in models.items():
            wins, losses = 0, 0
            for row in group_data:
                pred = model_func(row)
                if pred == 0: continue
                elif pred == row["RealBias"]: wins += 1
                else: losses += 1
                
            trades = wins + losses
            if trades < 4: continue # Require at least 4 trades to be statistically interesting
            
            win_rate = wins / trades
            results_for_group.append((name, win_rate, wins, trades))
            
            if win_rate > best_win_rate:
                best_win_rate = win_rate
                
        viable = [r for r in results_for_group if r[1] >= 0.80]
        viable.sort(key=lambda x: x[1], reverse=True)
        
        if viable:
            print(f"SUCCESS: Found {len(viable)} models >= 80% Win Rate for {group}:")
            for v in viable:
                print(f"   -> {v[1]*100:.1f}% ({v[2]}/{v[3]} trades) | {v[0]}")
        else:
            print(f"FAIL: No single model achieved >= 80% for {group}. Best was:")
            if results_for_group:
                best = max(results_for_group, key=lambda x: x[1])
                print(f"   -> {best[1]*100:.1f}% ({best[2]}/{best[3]} trades) | {best[0]}")
            else:
                print("   -> No models generated enough trades.")

if __name__ == "__main__":
    main()
