import sys
from pathlib import Path
import polars as pl
from datetime import datetime, timedelta

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

def predict_advanced(event_name, news_time, calendar):
    if "Farm" in event_name:
        adp = get_latest(calendar, "ADP Non-Farm Employment Change", news_time, 7)
        claims = get_latest(calendar, "Unemployment Claims", news_time, 7)
        ism_srv = get_latest(calendar, "ISM Services PMI", news_time, 7)
        score = calc_score(adp)*1.5 + calc_score(claims, True)*1.0 + calc_score(ism_srv)*1.0
        if score >= 1.0: return "BUY"
        if score <= -1.0: return "SELL"
        nfp = get_latest(calendar, "Non-Farm Employment Change", news_time + timedelta(minutes=1), 1)
        if nfp and nfp["forecast"] and nfp["previous"]: return "SELL" if nfp["forecast"] > nfp["previous"] else "BUY"
        return "SKIP"
        
    if "CPI" in event_name:
        wages = get_latest(calendar, "Average Hourly Earnings m/m", news_time, 14)
        ism_mfg = get_latest(calendar, "ISM Manufacturing PMI", news_time, 14)
        score = calc_score(wages)*1.5 + calc_score(ism_mfg)*1.0
        if score >= 1.0: return "BUY"
        if score <= -1.0: return "SELL"
        cpi = get_latest(calendar, "CPI m/m", news_time + timedelta(minutes=1), 1)
        if cpi and cpi["forecast"] and cpi["previous"]: return "SELL" if cpi["forecast"] > cpi["previous"] else "BUY"
        return "SKIP"

    if "Retail" in event_name:
        conf = get_latest(calendar, "CB Consumer Confidence", news_time, 30)
        score = calc_score(conf) * 2.0
        if score >= 1.0: return "BUY"
        if score <= -1.0: return "SELL"
        rs = get_latest(calendar, "Retail Sales m/m", news_time + timedelta(minutes=1), 1)
        if rs and rs["forecast"] and rs["previous"]: return "SELL" if rs["forecast"] > rs["previous"] else "BUY"
        return "SKIP"

    if "ISM" in event_name:
        empire = get_latest(calendar, "Empire State Manufacturing Index", news_time, 20)
        score = calc_score(empire) * 2.0
        if score >= 1.0: return "BUY"
        if score <= -1.0: return "SELL"
        ism = get_latest(calendar, event_name, news_time + timedelta(minutes=1), 1)
        if ism and ism["forecast"] and ism["previous"]: return "SELL" if ism["forecast"] > ism["previous"] else "BUY"
        return "SKIP"

    if "PCE" in event_name:
        cpi = get_latest(calendar, "CPI m/m", news_time, 20)
        score = calc_score(cpi) * 2.0
        if score >= 1.0: return "BUY"
        if score <= -1.0: return "SELL"
        pce = get_latest(calendar, event_name, news_time + timedelta(minutes=1), 1)
        if pce and pce["forecast"] and pce["previous"]: return "SELL" if pce["forecast"] > pce["previous"] else "BUY"
        return "SKIP"

    if "Federal Funds" in event_name:
        cpi = get_latest(calendar, "CPI m/m", news_time, 30)
        nfp = get_latest(calendar, "Non-Farm Employment Change", news_time, 30)
        score = calc_score(cpi) + calc_score(nfp)
        if score >= 1.0: return "BUY"
        if score <= -1.0: return "SELL"
        rate = get_latest(calendar, "Federal Funds Rate", news_time + timedelta(minutes=1), 1)
        if rate and rate["forecast"] and rate["previous"]: return "SELL" if rate["forecast"] > rate["previous"] else "BUY"
        return "SKIP"
        
    return "SKIP"

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
    
    settings = {"sl": 2.5, "trig": 5.0, "trail": 2.0}
    
    events_to_test = {
        "NFP": ["Non-Farm Employment Change"],
        "CPI": ["CPI m/m", "Core CPI m/m", "CPI y/y"],
        "Retail Sales": ["Retail Sales m/m", "Core Retail Sales m/m"],
        "ISM": ["ISM Manufacturing PMI", "ISM Services PMI"],
        "FOMC": ["Federal Funds Rate"],
        "PCE": ["Core PCE Price Index m/m"]
    }
    
    # We must construct a completely chronological timeline of events to simulate compounding properly
    all_events = []
    
    for group_name, event_names in events_to_test.items():
        dates = calendar.filter(pl.col("event").is_in(event_names))["timestamp"].dt.date().unique().to_list()
        for d in sorted(dates):
            if d.year < 2024: continue
            
            if group_name == "FOMC": window = prices.filter((pl.col("date") == d) & (pl.col("timestamp").dt.hour() >= 19))
            else: window = prices.filter((pl.col("date") == d) & (pl.col("timestamp").dt.hour() >= 13) & (pl.col("timestamp").dt.hour() <= 18))
            
            if window.height == 0: continue
            
            news_bar = window.sort("range", descending=True).head(1).to_dicts()[0]
            news_time = news_bar["timestamp"]
            entry_bar = prices.filter(pl.col("timestamp") < news_time).tail(1)
            
            if entry_bar.height == 0: continue
            
            adv_bias = predict_advanced(event_names[0], news_time, calendar)
            if adv_bias == "SKIP": continue
            
            all_events.append({
                "time": news_time,
                "group": group_name,
                "news_bar": news_bar,
                "entry_price": entry_bar["close"][0],
                "adv_bias": adv_bias
            })
            
    # Sort chronologically
    all_events.sort(key=lambda x: x["time"])
    
    # COMPOUNDING SIMULATION
    balance = 5000.0
    
    print("\n=== COMPOUNDING ASYMMETRIC STRADDLE SIMULATION ===")
    print("Starting Balance: $5,000")
    print("Rule: For every $5,000 in balance, risk $1000 (Bias) / $400 (Hedge)")
    print("="*85)
    
    peak_balance = balance
    blown = False
    
    for ev in all_events:
        # Calculate Compounding Units
        # The user said: "for every $5000 i will be risking 1000/400"
        # Meaning: $5k = 1 unit, $10k = 2 units, $15k = 3 units, etc.
        # We ensure a minimum of 1 unit as long as balance > 0 (or we could enforce strict $5k min, but let's allow playing with the remaining cash if we dip below 5k).
        units = max(1, int(balance // 5000))
        
        # In case they meant 1000/800 at 10k: Yes, 2 units * 400 = 800.
        risk_a = units * 1000
        risk_b = units * 400
        
        # Calculate Pip Values based on 250 pip SL
        pip_v_a = risk_a / 250.0
        pip_v_b = risk_b / 250.0
        
        # Simulate Trades
        opp_bias = "SELL" if ev["adv_bias"] == "BUY" else "BUY"
        pips_a = simulate_m1_trade(ev["entry_price"], ev["adv_bias"], ev["news_bar"], settings["sl"], settings["trig"], settings["trail"]) * 100
        pips_b = simulate_m1_trade(ev["entry_price"], opp_bias, ev["news_bar"], settings["sl"], settings["trig"], settings["trail"]) * 100
        
        usd_a = pips_a * pip_v_a
        usd_b = pips_b * pip_v_b
        net_usd = usd_a + usd_b
        
        balance += net_usd
        if balance > peak_balance: peak_balance = balance
        
        print(f"{str(ev['time'])[:16]} | {ev['group']:<6} | Unit:{units:<2} (Rsk ${risk_a}/${risk_b}) | Net: ${net_usd:9,.2f} | Bal: ${balance:9,.2f}")
        
        if balance <= 0:
            print(f"\n[!] ACCOUNT BLOWN on {str(ev['time'])[:16]}")
            blown = True
            break
            
    print("="*85)
    if not blown:
        print(f"FINAL BALANCE: ${balance:,.2f}")
        print(f"PEAK BALANCE:  ${peak_balance:,.2f}")
        print(f"TOTAL ROI:     {((balance - 5000) / 5000) * 100:,.1f}%")
    print("="*85 + "\n")

if __name__ == "__main__":
    main()
