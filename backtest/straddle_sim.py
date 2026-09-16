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
    
    # Check for instant double-whipsaw (both SLs hit in the same minute)
    # The backtester assumes worst case: if the candle expands past SL in the adverse direction, we take full SL loss.
    
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
    
    # 06:21 Global Settings
    settings = {"sl": 2.5, "trig": 5.0, "trail": 2.0}
    
    events_to_test = {
        "NFP": ["Non-Farm Employment Change"],
        "CPI": ["CPI m/m", "Core CPI m/m", "CPI y/y"],
        "Retail Sales": ["Retail Sales m/m", "Core Retail Sales m/m"],
        "ISM": ["ISM Manufacturing PMI", "ISM Services PMI"],
        "FOMC": ["Federal Funds Rate"],
        "PCE": ["Core PCE Price Index m/m"]
    }
    
    # Financial Params
    # Acct A (Bias): Risks $1000 for 250 pips SL -> Pip value = $4.00
    # Acct B (Hedge): Risks $400 for 250 pips SL -> Pip value = $1.60
    PIPV_A = 4.00
    PIPV_B = 1.60
    
    grand_total_usd = 0
    grand_wins = 0
    grand_losses = 0
    grand_whipsaws = 0
    
    print("\n=== ASYMMETRIC AI STRADDLE SIMULATION (2024-2026) ===")
    print("Account A (AI Bias): Risk $1,000 (Pip Value $4.00)")
    print("Account B (Hedge):   Risk $400   (Pip Value $1.60)")
    print("Global Settings: SL 250 | Trig 500 | Trail 200")
    print("="*75)
    
    for group_name, event_names in events_to_test.items():
        dates = calendar.filter(pl.col("event").is_in(event_names))["timestamp"].dt.date().unique().to_list()
        
        grp_usd = 0
        
        for d in sorted(dates):
            if d.year < 2024: continue
            
            if group_name == "FOMC": window = prices.filter((pl.col("date") == d) & (pl.col("timestamp").dt.hour() >= 19))
            else: window = prices.filter((pl.col("date") == d) & (pl.col("timestamp").dt.hour() >= 13) & (pl.col("timestamp").dt.hour() <= 18))
            if window.height == 0: continue
            
            news_bar = window.sort("range", descending=True).head(1).to_dicts()[0]
            news_time = news_bar["timestamp"]
            entry_bar = prices.filter(pl.col("timestamp") < news_time).tail(1)
            if entry_bar.height == 0: continue
            
            entry_price = entry_bar["close"][0]
            
            # Predict
            adv_bias = predict_advanced(event_names[0], news_time, calendar)
            if adv_bias == "SKIP": continue
                
            opp_bias = "SELL" if adv_bias == "BUY" else "BUY"
            
            # Simulate both trades
            pips_a = simulate_m1_trade(entry_price, adv_bias, news_bar, settings["sl"], settings["trig"], settings["trail"]) * 100
            pips_b = simulate_m1_trade(entry_price, opp_bias, news_bar, settings["sl"], settings["trig"], settings["trail"]) * 100
            
            # Convert to USD
            usd_a = pips_a * PIPV_A
            usd_b = pips_b * PIPV_B
            net_usd = usd_a + usd_b
            
            status = ""
            if pips_a <= -250 and pips_b <= -250:
                status = "DOUBLE WHIPSAW (Both SL hit)"
                grand_whipsaws += 1
            elif net_usd > 0:
                if pips_a > 0: status = "WIN (AI Bias Correct)"
                else: status = "WIN (Hedge Saved Us)"
                grand_wins += 1
            else:
                status = "LOSS"
                grand_losses += 1
                
            print(f"{str(news_time)[:16]} | {group_name:<12} | AI:{adv_bias:<4} | Net: ${net_usd:,.2f} | {status}")
            grp_usd += net_usd
            grand_total_usd += net_usd
            
        #print(f"--- {group_name} Total: ${grp_usd:,.2f} ---")
        
    print("="*75)
    print(f"TOTAL TRADES: {grand_wins + grand_losses + grand_whipsaws}")
    print(f"PROFITABLE EVENTS: {grand_wins}")
    print(f"LOSING EVENTS: {grand_losses}")
    print(f"DOUBLE WHIPSAWS (Both Accounts Blown): {grand_whipsaws}")
    print(f"GRAND TOTAL NET PROFIT: ${grand_total_usd:,.2f}")
    print("="*75 + "\n")

if __name__ == "__main__":
    main()
