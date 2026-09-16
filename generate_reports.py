import sys
import csv
from pathlib import Path
import polars as pl
from datetime import datetime, timedelta
import plotly.graph_objects as go
import plotly.io as pio

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data.load_prices import load_xauusd_prices
from backtest.final_summary import predict_advanced, simulate_m1_trade_realistic, get_latest

def main():
    project_root = Path(__file__).resolve().parent
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
        "Retail Sales": ["Retail Sales m/m", "Core Retail Sales m/m"]
    }
    
    all_events = []
    for group_name, event_names in events_to_test.items():
        dates = calendar.filter(pl.col("event").is_in(event_names))["timestamp"].dt.date().unique().to_list()
        for d in sorted(dates):
            if d.year < 2024: continue
            window = prices.filter((pl.col("date") == d) & (pl.col("timestamp").dt.hour() >= 13) & (pl.col("timestamp").dt.hour() <= 18))
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
            
    all_events.sort(key=lambda x: x["time"])
    
    total_pot = 5000.0
    history = []
    stats = {g: {"wins": 0, "losses": 0, "usd": 0.0} for g in events_to_test.keys()}
    
    equity_dates = [all_events[0]["time"] - timedelta(days=1)]
    equity_values = [5000.0]
    
    for ev in all_events:
        if total_pot < 10000.0:
            alloc_a, alloc_b = 1000.0, 500.0
        else:
            units = int(total_pot // 5000)
            alloc_a, alloc_b = units * 1000.0, units * 500.0
            
        lots_a, lots_b = (alloc_a / 4.0) * 0.01, (alloc_b / 4.0) * 0.01
        opp_bias = "SELL" if ev["adv_bias"] == "BUY" else "BUY"
        
        move_a = simulate_m1_trade_realistic(ev["entry_price"], ev["adv_bias"], ev["news_bar"], settings["sl"], settings["trig"], settings["trail"])
        move_b = simulate_m1_trade_realistic(ev["entry_price"], opp_bias, ev["news_bar"], settings["sl"], settings["trig"], settings["trail"])
        
        net = (move_a * lots_a * 100.0) + (move_b * lots_b * 100.0)
        total_pot += net
        
        if net > 0: stats[ev['group']]["wins"] += 1
        else: stats[ev['group']]["losses"] += 1
        stats[ev['group']]["usd"] += net
        
        history.append({
            "Date": str(ev['time'])[:16],
            "Event": ev['group'],
            "AI_Bias": ev['adv_bias'],
            "Net_Profit_USD": round(net, 2),
            "Total_Pot": round(total_pot, 2)
        })
        
        equity_dates.append(ev["time"])
        equity_values.append(total_pot)
        
    # Write Trade History CSV
    with open("reports/trade_history.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["Date", "Event", "AI_Bias", "Net_Profit_USD", "Total_Pot"])
        writer.writeheader()
        writer.writerows(history)
        
    # Write Stats CSV
    with open("reports/event_statistics.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Event", "Total_Trades", "Wins", "Losses", "Win_Rate_%", "Total_Produced_USD"])
        for ev, s in stats.items():
            tot = s["wins"] + s["losses"]
            wr = (s["wins"] / tot * 100) if tot > 0 else 0
            writer.writerow([ev, tot, s["wins"], s["losses"], round(wr, 2), round(s["usd"], 2)])
            
    # Generate Equity Graph
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=equity_dates, y=equity_values, mode='lines+markers', name='Equity', line=dict(color='#00ff00', width=3)))
    fig.update_layout(
        title="Straddle Equity Curve (Holy Trinity Only)",
        xaxis_title="Date",
        yaxis_title="Total Equity (USD)",
        template="plotly_dark",
        yaxis=dict(tickprefix="$", tickformat=",.0f")
    )
    fig.write_image("reports/equity_graph.png", scale=2)
    print("Reports generated successfully in /reports")

if __name__ == "__main__":
    main()
