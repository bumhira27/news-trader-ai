import sys
from pathlib import Path
import polars as pl
from itertools import product

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

def get_event_dates(df_cal, event_names):
    dates = df_cal.filter(pl.col("event").is_in(event_names))["timestamp"].dt.date().unique().to_list()
    return sorted(dates)

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
    
    event_groups = {
        "NFP": ["Non-Farm Employment Change"],
        "CPI": ["CPI m/m", "Core CPI m/m", "CPI y/y"],
        "Retail Sales": ["Retail Sales m/m", "Core Retail Sales m/m"],
        "ISM": ["ISM Manufacturing PMI", "ISM Services PMI"],
        "FOMC": ["Federal Funds Rate"],
        "PCE": ["Core PCE Price Index m/m"]
    }
    
    # Define Parameter Grid
    # SL: 150 to 300 pips
    # Trigger: 200 to 1200 pips
    # Trail: 100 to 400 pips
    sl_options = [1.5, 2.0, 2.5, 3.0]
    trigger_options = [2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0, 12.0]
    trail_options = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0]
    
    print("Optimizing parameters based on theoretical optimal entry to isolate trailing mechanics...")
    
    for group_name, event_names in event_groups.items():
        dates = get_event_dates(calendar, event_names)
        events_data = []
        
        for d in dates:
            if d.year < 2024: continue
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
            bias = "BUY" if news_bar_row["close"] > entry_price else "SELL"
            
            events_data.append((entry_price, bias, news_bar_row))
            
        if not events_data: continue
        
        best_pnl = -999999
        best_params = None
        best_winrate = 0
        
        for sl, trig, trail in product(sl_options, trigger_options, trail_options):
            if trail >= trig: continue # Trail step must be smaller than trigger
            
            total_pnl = 0
            wins = 0
            for entry, bias, bar in events_data:
                pnl = simulate_m1_trade(entry, bias, bar, sl, trig, trail)
                pips = round(pnl * 100)
                total_pnl += pips
                if pips > 0: wins += 1
                
            if total_pnl > best_pnl:
                best_pnl = total_pnl
                best_params = (sl, trig, trail)
                best_winrate = wins / len(events_data)
                
        sl, trig, trail = best_params
        print(f"\n--- BEST SETTINGS FOR {group_name.upper()} ---")
        print(f"Stop Loss:        {int(sl*100)} pips")
        print(f"Trailing Trigger: {int(trig*100)} pips")
        print(f"Trailing Step:    {int(trail*100)} pips")
        print(f"Maximized Profit: +{best_pnl} Pips")
        print(f"Optimal Win Rate: {best_winrate*100:.1f}%")

if __name__ == "__main__":
    main()
