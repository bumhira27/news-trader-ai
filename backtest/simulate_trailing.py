import sys
from pathlib import Path
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data.load_prices import load_xauusd_prices
from backtest.event_backtest import filter_target_events, map_event_category
from backtest.fast_optimize import compute_technicals, custom_scorecard

def simulate_trade(entry_price, direction, prices_30m, sl_pips, trigger_pips, trail_dist_pips):
    sl_usd = sl_pips / 100.0
    trigger_usd = trigger_pips / 100.0
    trail_dist_usd = trail_dist_pips / 100.0
    
    if direction == "BUY":
        current_sl = entry_price - sl_usd
        trail_activated = False
        
        for row in prices_30m.iter_rows(named=True):
            high = row["high"]
            low = row["low"]
            close = row["close"]
            
            if low <= current_sl:
                return current_sl - entry_price 
                
            if not trail_activated and high >= entry_price + trigger_usd:
                trail_activated = True
                new_sl = high - trail_dist_usd
                if new_sl > current_sl: current_sl = new_sl
            elif trail_activated:
                new_sl = high - trail_dist_usd
                if new_sl > current_sl: current_sl = new_sl
                
        return prices_30m["close"][-1] - entry_price

    else: 
        current_sl = entry_price + sl_usd
        trail_activated = False
        
        for row in prices_30m.iter_rows(named=True):
            high = row["high"]
            low = row["low"]
            close = row["close"]
            
            if high >= current_sl:
                return entry_price - current_sl
                
            if not trail_activated and low <= entry_price - trigger_usd:
                trail_activated = True
                new_sl = low + trail_dist_usd
                if new_sl < current_sl: current_sl = new_sl
            elif trail_activated:
                new_sl = low + trail_dist_usd
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
            history.append({"date": t["timestamp"], "event": t["event_category"], "pnl": 0, "balance": balance, "note": "BLOWN"})
            break
            
        pnl_per_ounce = simulate_trade(t["entry_price"], t["direction"], t["prices_30m"], sl_pips, trigger_pips, trail_dist_pips)
        
        trade_profit = pnl_per_ounce * ounces
        trade_profit -= (0.15 * ounces)
        
        balance += trade_profit
        note = "WIN" if trade_profit > 0 else "LOSS"
        
        withdrawn = 0.0
        if trade_profit > 0:
            withdrawn = trade_profit * 0.50
            balance -= withdrawn
            
        history.append({
            "date": t["timestamp"], 
            "event": t["event_category"], 
            "direction": t["direction"],
            "ounces": round(ounces, 1),
            "pnl": round(trade_profit, 2), 
            "withdrawn": round(withdrawn, 2),
            "balance": round(balance, 2), 
            "note": note
        })
        
    return history

def main():
    project_root = Path(__file__).resolve().parent.parent
    calendar = filter_target_events(pl.read_parquet(project_root / "data" / "calendar_usd_high.parquet"))
    macro_context = pl.read_parquet(project_root / "data" / "macro_context.parquet")
    prices = compute_technicals(load_xauusd_prices([
        r"C:\Users\bumhira27\Downloads\XAUUSD_2024_all.csv",
        r"C:\Users\bumhira27\Downloads\XAUUSD_2025_all.csv",
        r"C:\Users\bumhira27\Downloads\XAUUSD_2026\*.csv"
    ]))
    
    cal, pr = calendar.clone(), prices.clone()
    cal = cal.rename({"datetime": "timestamp"}) if "datetime" in cal.columns else cal
    aligned = cal.sort("timestamp").join_asof(pr.sort("timestamp"), on="timestamp", strategy="backward", tolerance="5m")
    aligned = aligned.filter(pl.col("close").is_not_null())
    aligned = aligned.join_asof(macro_context, on="timestamp", strategy="backward")
    aligned = aligned.with_columns(pl.col("event").map_elements(map_event_category, return_dtype=pl.Utf8).alias("event_category"))
    
    best_weights = {"labor_wt": 1.5, "growth_wt": 1.0, "yield_wt": 1.5, "yield_hi": 4.5, "yield_lo": 4.0, "threshold": 1.0}
    
    trades = []
    
    for row in aligned.to_dicts():
        cat = row["event_category"]
        if cat not in ["NFP", "Retail Sales", "ISM"]: continue
        
        rsi = row.get("rsi_14")
        if cat == "ISM":
            if rsi is None or (40 <= rsi <= 60): continue
            
        score, bias = custom_scorecard(row, best_weights)
        if bias == "SKIP": continue
        
        entry_time = row["timestamp"]
        end_time = entry_time + pl.duration(minutes=30)
        window = prices.filter((pl.col("timestamp") > entry_time) & (pl.col("timestamp") <= end_time))
        if window.height == 0: continue
        
        trades.append({
            "timestamp": entry_time,
            "event_category": cat,
            "direction": bias,
            "entry_price": row["close"], 
            "prices_30m": window
        })
        
    trades.sort(key=lambda x: x["timestamp"])
    
    setups = [
        {"name": "Setup 1 (Yours)", "sl": 200, "trigger": 300, "trail": 200},
        {"name": "Setup 2 (Yours)", "sl": 250, "trigger": 500, "trail": 200},
        {"name": "Setup 3 (My Rec)", "sl": 250, "trigger": 400, "trail": 150} 
    ]
    
    for s in setups:
        print(f"\n{'='*60}")
        print(f"Running {s['name']}: SL {s['sl']} | Trigger {s['trigger']} | Trail {s['trail']}")
        print(f"{'='*60}")
        hist = run_account_simulation(trades, s['sl'], s['trigger'], s['trail'])
        
        total_withdrawn = sum(h.get("withdrawn", 0) for h in hist)
        final_balance = hist[-1]["balance"] if hist else 0
        total_profit = (final_balance + total_withdrawn) - 100
        wins = sum(1 for h in hist if h["note"] == "WIN")
        losses = sum(1 for h in hist if h["note"] == "LOSS")
        
        print(f"{'Date':<20} | {'Event':<15} | {'PnL':<8} | {'Draw':<8} | {'Bal':<8}")
        print("-" * 65)
        for h in hist:
            print(f"{str(h['date'])[:16]:<20} | {h['event']:<15} | {h.get('pnl', 0):<8.2f} | {h.get('withdrawn', 0):<8.2f} | {h['balance']:<8.2f}")
            
        print("-" * 65)
        print(f"Total Trades : {wins + losses}")
        print(f"Wins / Losses: {wins} / {losses}")
        print(f"Total Withdrawn: ${total_withdrawn:.2f}")
        print(f"Final Balance: ${final_balance:.2f}")

if __name__ == "__main__":
    main()
