import sys
from pathlib import Path
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data.load_prices import load_xauusd_prices
from backtest.event_backtest import filter_target_events, map_event_category, backtest_pre_release_scorecard

def simulate_m1_trade(entry_price, direction, news_bar, sl_pips, trigger_pips, trail_dist_pips):
    sl_usd = sl_pips / 100.0
    trigger_usd = trigger_pips / 100.0
    trail_dist_usd = trail_dist_pips / 100.0
    
    high = news_bar["high"][0]
    low = news_bar["low"][0]
    close = news_bar["close"][0]
    
    if direction == "BUY":
        current_sl = entry_price - sl_usd
        
        if low <= current_sl:
            return current_sl - entry_price
            
        if high >= entry_price + trigger_usd:
            new_sl = high - trail_dist_usd
            if new_sl >= close:
                return new_sl - entry_price
            else:
                return close - entry_price
        else:
            return close - entry_price

    else: 
        current_sl = entry_price + sl_usd
        
        if high >= current_sl:
            return entry_price - current_sl
            
        if low <= entry_price - trigger_usd:
            new_sl = low + trail_dist_usd
            if new_sl <= close:
                return entry_price - new_sl
            else:
                return entry_price - close
        else:
            return entry_price - close

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
    
    res_score = backtest_pre_release_scorecard(aligned, prices, macro)
    res_score = res_score.with_columns(pl.col("event").map_elements(map_event_category, return_dtype=pl.Utf8).alias("event_category"))
    
    print(f"\n--- M1 CANDLE ONLY SIMULATION ---")
    print(f"{'Date':<18} | {'Event':<15} | {'Dir':<4} | {'Entry':<8} | {'M1 High':<8} | {'M1 Low':<8} | {'M1 Close':<8} | {'PnL_pips':<8}")
    print("-" * 90)
    
    total_pips = 0
    wins = 0
    losses = 0
    
    for row in res_score.to_dicts():
        cat = row["event_category"]
        if cat != "NFP": continue
            
        entry_time = row["timestamp"]
        
        entry_bar = prices.filter(pl.col("timestamp") < entry_time).tail(1)
        if entry_bar.height == 0: continue
        entry_price = entry_bar["close"][0]
        
        news_bar = prices.filter(pl.col("timestamp") == entry_time)
        if news_bar.height == 0: continue
        
        pnl_usd = simulate_m1_trade(entry_price, row["predicted_direction"], news_bar, 200, 600, 200)
        pnl_pips = round(pnl_usd * 100)
        
        total_pips += pnl_pips
        if pnl_pips > 0: wins += 1
        else: losses += 1
        
        print(f"{str(entry_time)[:16]:<18} | {cat:<15} | {row['predicted_direction']:<4} | {entry_price:<8.2f} | {news_bar['high'][0]:<8.2f} | {news_bar['low'][0]:<8.2f} | {news_bar['close'][0]:<8.2f} | {pnl_pips:<8}")
        
    print("-" * 90)
    print(f"Total NFP M1 Trades: {wins + losses} ({wins} Wins / {losses} Losses)")
    print(f"Total Net Pips: {total_pips}")

if __name__ == "__main__":
    main()
