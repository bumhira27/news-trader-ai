import sys
from pathlib import Path
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data.load_prices import load_xauusd_prices
from backtest.event_backtest import filter_target_events, map_event_category, backtest_pre_release_scorecard

def simulate_trade(entry_price, direction, prices_30m, sl_pips, trigger_pips, trail_dist_pips):
    sl_usd = sl_pips / 100.0
    trigger_usd = trigger_pips / 100.0
    trail_dist_usd = trail_dist_pips / 100.0
    
    if direction == "BUY":
        current_sl = entry_price - sl_usd
        trail_activated = False
        for row in prices_30m.iter_rows(named=True):
            if row["low"] <= current_sl: return current_sl - entry_price 
            if not trail_activated and row["high"] >= entry_price + trigger_usd:
                trail_activated = True
                new_sl = row["high"] - trail_dist_usd
                if new_sl > current_sl: current_sl = new_sl
            elif trail_activated:
                new_sl = row["high"] - trail_dist_usd
                if new_sl > current_sl: current_sl = new_sl
        return prices_30m["close"][-1] - entry_price
    else: 
        current_sl = entry_price + sl_usd
        trail_activated = False
        for row in prices_30m.iter_rows(named=True):
            if row["high"] >= current_sl: return entry_price - current_sl
            if not trail_activated and row["low"] <= entry_price - trigger_usd:
                trail_activated = True
                new_sl = row["low"] + trail_dist_usd
                if new_sl < current_sl: current_sl = new_sl
            elif trail_activated:
                new_sl = row["low"] + trail_dist_usd
                if new_sl < current_sl: current_sl = new_sl
        return entry_price - prices_30m["close"][-1]

def run_account_simulation(trades, sl_pips, trigger_pips, trail_dist_pips):
    balance = 100.0
    history = []
    for t in trades:
        risk_usd = balance * 0.80
        sl_usd = sl_pips / 100.0
        ounces_by_risk = risk_usd / sl_usd
        ounces_by_margin = balance / 4.0
        ounces = min(ounces_by_risk, ounces_by_margin)
        
        if ounces < 1.0:
            history.append({"date": t["timestamp"], "event": t["event"], "pnl": 0, "balance": balance, "note": "BLOWN"})
            continue
            
        pnl_per_ounce = simulate_trade(t["entry_price"], t["direction"], t["prices_30m"], sl_pips, trigger_pips, trail_dist_pips)
        trade_profit = (pnl_per_ounce * ounces) - (0.15 * ounces)
        balance += trade_profit
        
        note = "WIN" if trade_profit > 0 else "LOSS"
        withdrawn = 0.0
        if trade_profit > 0:
            withdrawn = trade_profit * 0.50
            balance -= withdrawn
            
        history.append({
            "date": t["timestamp"], "event": t["event"], "direction": t["direction"],
            "ounces": round(ounces, 1), "pnl": round(trade_profit, 2), 
            "withdrawn": round(withdrawn, 2), "balance": round(balance, 2), "note": note
        })
    return history

def compute_rsi(prices: pl.DataFrame) -> pl.DataFrame:
    delta = pl.col("close").diff()
    up = pl.when(delta > 0).then(delta).otherwise(0.0)
    down = pl.when(delta < 0).then(-delta).otherwise(0.0)
    rs = up.rolling_mean(14) / down.rolling_mean(14)
    return prices.with_columns((100 - (100 / (1 + rs))).alias("rsi_14"))

def main():
    project_root = Path(__file__).resolve().parent.parent
    calendar = filter_target_events(pl.read_parquet(project_root / "data" / "calendar_usd_high.parquet"))
    macro = pl.read_parquet(project_root / "data" / "macro_context.parquet")
    prices = load_xauusd_prices([
        r"C:\Users\bumhira27\Downloads\XAUUSD_2024_all.csv",
        r"C:\Users\bumhira27\Downloads\XAUUSD_2025_all.csv",
        r"C:\Users\bumhira27\Downloads\XAUUSD_2026\*.csv"
    ])
    
    cal, pr = calendar.clone(), prices.clone()
    cal = cal.rename({"datetime": "timestamp"}) if "datetime" in cal.columns else cal
    aligned = cal.sort("timestamp").join_asof(pr.sort("timestamp"), on="timestamp", strategy="backward", tolerance="5m")
    aligned = aligned.filter(pl.col("close").is_not_null())
    
    print("Generating baseline predictions using exact original logic...")
    res_score = backtest_pre_release_scorecard(aligned, prices, macro)
    res_score = res_score.with_columns(pl.col("event").map_elements(map_event_category, return_dtype=pl.Utf8).alias("event_category"))
    
    print("Computing RSI for ISM filter...")
    pr_rsi = compute_rsi(prices)
    res_score = res_score.join_asof(pr_rsi.select(["timestamp", "rsi_14"]), on="timestamp", strategy="backward")
    
    trades = []
    for row in res_score.to_dicts():
        cat = row["event_category"]
        if cat not in ["NFP", "Retail Sales", "ISM"]: continue
        
        if cat == "ISM":
            rsi = row.get("rsi_14")
            if rsi is None or (40 <= rsi <= 60): continue
            
        entry_time = row["timestamp"]
        window = prices.filter((pl.col("timestamp") > entry_time) & (pl.col("timestamp") <= entry_time + pl.duration(minutes=30)))
        if window.height == 0: continue
        
        trades.append({
            "timestamp": entry_time, "event": cat, "direction": row["predicted_direction"],
            "entry_price": row["close"], "prices_30m": window
        })
        
    trades.sort(key=lambda x: x["timestamp"])
    print(f"Total Valid Trades Extracted for Simulation: {len(trades)}")
    
    hist = run_account_simulation(trades, 250, 400, 150)
    
    total_withdrawn = sum(h.get("withdrawn", 0) for h in hist)
    final_balance = hist[-1]["balance"] if hist else 0
    
    print(f"\n{'Date':<20} | {'Event':<15} | {'PnL':<8} | {'Draw':<8} | {'Bal':<8}")
    print("-" * 65)
    for h in hist:
        print(f"{str(h['date'])[:16]:<20} | {h['event']:<15} | {h.get('pnl', 0):<8.2f} | {h.get('withdrawn', 0):<8.2f} | {h['balance']:<8.2f}")
    
    nfp_w = sum(1 for h in hist if h["event"] == "NFP" and h["note"] == "WIN")
    nfp_l = sum(1 for h in hist if h["event"] == "NFP" and h["note"] == "LOSS")
    ret_w = sum(1 for h in hist if h["event"] == "Retail Sales" and h["note"] == "WIN")
    ret_l = sum(1 for h in hist if h["event"] == "Retail Sales" and h["note"] == "LOSS")
    ism_w = sum(1 for h in hist if h["event"] == "ISM" and h["note"] == "WIN")
    ism_l = sum(1 for h in hist if h["event"] == "ISM" and h["note"] == "LOSS")
    
    print("\n--- ACTUAL TRADE COUNTS IN SIMULATION ---")
    print(f"NFP: {nfp_w + nfp_l} trades ({nfp_w} Wins / {nfp_l} Losses)")
    print(f"Retail Sales: {ret_w + ret_l} trades ({ret_w} Wins / {ret_l} Losses)")
    print(f"ISM (Filtered): {ism_w + ism_l} trades ({ism_w} Wins / {ism_l} Losses)")

if __name__ == "__main__":
    main()
