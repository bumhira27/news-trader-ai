import sys
from pathlib import Path
import polars as pl
from datetime import datetime

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

def run_setups(trades):
    setups = [
        {"name": "Setup A (SL 200 | Trig 300 | Trail 200)", "sl": 2.0, "trig": 3.0, "trail": 2.0},
        {"name": "Setup B (SL 250 | Trig 500 | Trail 200)", "sl": 2.5, "trig": 5.0, "trail": 2.0},
        {"name": "My Rec (SL 200 | Trig 150 | Trail 50)", "sl": 2.0, "trig": 1.5, "trail": 0.5}
    ]
    
    for s in setups:
        print(f"\n--- {s['name']} ---")
        print(f"{'Date':<18} | {'PnL Pips':<8}")
        print("-" * 30)
        total_pips = 0
        wins = 0
        losses = 0
        for t in trades:
            pnl_usd = simulate_m1_trade(t['entry'], t['bias'], t['bar'], s['sl'], s['trig'], s['trail'])
            pips = round(pnl_usd * 100)
            total_pips += pips
            if pips > 0: wins += 1
            else: losses += 1
            print(f"{str(t['time'])[:16]:<18} | {pips:<8}")
        print("-" * 30)
        print(f"Total Net Pips: {total_pips} ({wins} W / {losses} L)")

def main():
    prices = load_xauusd_prices([
        r"C:\Users\bumhira27\Downloads\XAUUSD_2024_all.csv",
        r"C:\Users\bumhira27\Downloads\XAUUSD_2025_all.csv",
        r"C:\Users\bumhira27\Downloads\XAUUSD_2026\*.csv"
    ])
    
    # Official NFP dates
    nfp_dates = [
        datetime(2024, 1, 5), datetime(2024, 2, 2), datetime(2024, 3, 8), 
        datetime(2024, 4, 5), datetime(2024, 5, 3), datetime(2024, 6, 7), 
        datetime(2024, 7, 5), datetime(2024, 8, 2), datetime(2024, 9, 6), 
        datetime(2024, 10, 4), datetime(2024, 11, 1), datetime(2024, 12, 6),
        datetime(2025, 1, 10), datetime(2025, 2, 7), datetime(2025, 3, 7), datetime(2025, 4, 4)
    ]
    
    # Simple hardcoded pre-release biases based on strong/weak historical forecast vs actual
    # Real EA will fetch this from the FRED API or a live calendar 3 seconds before
    # For backtesting the M1 mechanics, we assume perfect hindsight direction to test the trailing stop logic.
    nfp_bias = {
        (2024, 1): "BUY", (2024, 2): "SELL", (2024, 3): "SELL", (2024, 4): "SELL",
        (2024, 5): "BUY", (2024, 6): "SELL", (2024, 7): "BUY", (2024, 8): "BUY",
        (2024, 9): "BUY", (2024, 10): "SELL", (2024, 11): "BUY", (2024, 12): "BUY",
        (2025, 1): "BUY", (2025, 2): "BUY", (2025, 3): "BUY", (2025, 4): "BUY"
    }
    
    trades = []
    
    for d in nfp_dates:
        # Find the massive volume/range spike between 14:00 and 16:00
        window = prices.filter(
            (pl.col("timestamp") >= d.replace(hour=14, minute=0)) & 
            (pl.col("timestamp") <= d.replace(hour=16, minute=0))
        ).with_columns((pl.col('high') - pl.col('low')).alias('range'))
        
        if window.height == 0: continue
        
        news_bar_row = window.sort('range', descending=True).head(1).to_dicts()[0]
        news_time = news_bar_row["timestamp"]
        
        # Entry price is the close of the bar exactly before
        entry_bar = prices.filter(pl.col("timestamp") < news_time).tail(1)
        if entry_bar.height == 0: continue
        entry_price = entry_bar["close"][0]
        
        bias = nfp_bias.get((d.year, d.month), "BUY")
        
        trades.append({
            "time": news_time,
            "bias": bias,
            "entry": entry_price,
            "bar": news_bar_row
        })
        
    trades.sort(key=lambda x: x["time"])
    
    print("\n=== TRUE NFP M1 CANDLES ===")
    print(f"{'Date':<18} | {'Entry':<8} | {'High':<8} | {'Low':<8} | {'Close':<8} | {'Range(pips)':<10}")
    print("-" * 75)
    for t in trades:
        rng = round(t['bar']['range'] * 100)
        print(f"{str(t['time'])[:16]:<18} | {t['entry']:<8.2f} | {t['bar']['high']:<8.2f} | {t['bar']['low']:<8.2f} | {t['bar']['close']:<8.2f} | {rng:<10}")
        
    run_setups(trades)

if __name__ == "__main__":
    main()
