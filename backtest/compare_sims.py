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
    
    # 06:21 Model Settings
    m1_settings = {"sl": 2.5, "trig": 5.0, "trail": 2.0}
    
    # Advanced Model Settings
    adv_settings = {
        "NFP": {"sl": 2.5, "trig": 7.0, "trail": 2.0},
        "CPI": {"sl": 2.5, "trig": 6.0, "trail": 2.0},
        "Retail Sales": {"sl": 2.0, "trig": 3.5, "trail": 1.5},
        "ISM": {"sl": 2.0, "trig": 3.0, "trail": 1.5},
        "FOMC": {"sl": 2.5, "trig": 5.0, "trail": 1.5},
        "PCE": {"sl": 1.5, "trig": 2.5, "trail": 1.0}
    }
    
    events_to_test = {
        "NFP": ["Non-Farm Employment Change"],
        "CPI": ["CPI m/m", "Core CPI m/m", "CPI y/y"],
        "Retail Sales": ["Retail Sales m/m", "Core Retail Sales m/m"],
        "ISM": ["ISM Manufacturing PMI", "ISM Services PMI"],
        "FOMC": ["Federal Funds Rate"],
        "PCE": ["Core PCE Price Index m/m"]
    }
    
    results = []
    
    for group_name, event_names in events_to_test.items():
        dates = calendar.filter(pl.col("event").is_in(event_names))["timestamp"].dt.date().unique().to_list()
        for d in sorted(dates):
            if d.year < 2024: continue
            
            if group_name == "FOMC":
                window = prices.filter((pl.col("date") == d) & (pl.col("timestamp").dt.hour() >= 19))
            else:
                window = prices.filter((pl.col("date") == d) & (pl.col("timestamp").dt.hour() >= 13) & (pl.col("timestamp").dt.hour() <= 18))
                
            if window.height == 0: continue
            
            news_bar = window.sort("range", descending=True).head(1).to_dicts()[0]
            news_time = news_bar["timestamp"]
            entry_bar = prices.filter(pl.col("timestamp") < news_time).tail(1)
            if entry_bar.height == 0: continue
            entry_price = entry_bar["close"][0]
            
            real_bias = "BUY" if news_bar["close"] > entry_price else "SELL"
            adv_bias = predict_advanced(event_names[0], news_time, calendar)
            if adv_bias == "SKIP": continue
            
            # 1. 06:21 Model (Perfect Bias + Global Settings)
            pnl_m1 = simulate_m1_trade(entry_price, real_bias, news_bar, m1_settings["sl"], m1_settings["trig"], m1_settings["trail"])
            
            # 2. Advanced Model (Predicted Bias + Custom Settings)
            s = adv_settings[group_name]
            pnl_adv = simulate_m1_trade(entry_price, adv_bias, news_bar, s["sl"], s["trig"], s["trail"])
            
            results.append({
                "Group": group_name,
                "Date": news_time,
                "Range": round(news_bar["range"] * 100),
                "RealBias": real_bias,
                "AdvBias": adv_bias,
                "M1_PnL": round(pnl_m1 * 100),
                "Adv_PnL": round(pnl_adv * 100),
            })
            
    print("\n" + "="*85)
    print(f" SIDE-BY-SIDE COMPARISON: 06:21 M1 SCALP (PERFECT BIAS) vs ADVANCED PREDICTION ")
    print("="*85)
    
    total_m1_pips, total_adv_pips = 0, 0
    m1_wins, adv_wins = 0, 0
    m1_loss, adv_loss = 0, 0
    
    for group in events_to_test.keys():
        grp_results = [r for r in results if r["Group"] == group]
        if not grp_results: continue
        
        print(f"\n--- {group.upper()} ---")
        print(f"{'Date':<11} | {'M1 SCALP (06:21)':<30} || {'ADVANCED PREDICTIVE':<30}")
        print("-" * 85)
        
        grp_m1_pips, grp_adv_pips = 0, 0
        gw_m1, gl_m1 = 0, 0
        gw_adv, gl_adv = 0, 0
        
        for r in grp_results:
            d = str(r['Date'].date())
            
            # M1 Setup Data
            m1_res = "WIN" if r['M1_PnL'] > 0 else "LOSS"
            m1_str = f"Dir: {r['RealBias']:<4} | {r['M1_PnL']:>5} pips ({m1_res})"
            grp_m1_pips += r['M1_PnL']
            if r['M1_PnL'] > 0: gw_m1 += 1
            else: gl_m1 += 1
            
            # Adv Setup Data
            adv_res = "WIN" if r['Adv_PnL'] > 0 else "LOSS"
            adv_acc = "Y" if r['AdvBias'] == r['RealBias'] else "N"
            adv_str = f"Dir: {r['AdvBias']:<4} {adv_acc} | {r['Adv_PnL']:>5} pips ({adv_res})"
            grp_adv_pips += r['Adv_PnL']
            if r['Adv_PnL'] > 0: gw_adv += 1
            else: gl_adv += 1
            
            print(f"{d:<11} | {m1_str:<30} || {adv_str:<30}")
            
        print("-" * 85)
        print(f"TOTAL:      | {grp_m1_pips:>6} Pips ({gw_m1} W / {gl_m1} L)         || {grp_adv_pips:>6} Pips ({gw_adv} W / {gl_adv} L)")
        
        total_m1_pips += grp_m1_pips
        total_adv_pips += grp_adv_pips
        m1_wins += gw_m1; m1_loss += gl_m1
        adv_wins += gw_adv; adv_loss += gl_adv

    print("\n" + "="*85)
    print(" GRAND TOTALS ")
    print("="*85)
    print(f"M1 SCALP (PERFECT BIAS):   {total_m1_pips:>7} Pips ({m1_wins} Wins / {m1_loss} Losses) | Win Rate: {m1_wins/(m1_wins+m1_loss)*100:.1f}%")
    print(f"ADVANCED PREDICTIVE BOT:   {total_adv_pips:>7} Pips ({adv_wins} Wins / {adv_loss} Losses) | Win Rate: {adv_wins/(adv_wins+adv_loss)*100:.1f}%")
    print("="*85 + "\n")

if __name__ == "__main__":
    main()
