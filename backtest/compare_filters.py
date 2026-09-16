
import polars as pl
from pathlib import Path
from tabulate import tabulate

def calc_metrics(df: pl.DataFrame):
    if df.height == 0:
        return 0, 0.0
    mfe = df["mfe_30m"].drop_nulls().mean() or 0.0
    mae = df["mae_30m"].drop_nulls().mean() or 0.0
    pf = mfe / mae if mae > 0 else 0.0
    return df.height, pf

def main():
    project_root = Path(__file__).resolve().parent.parent
    csv_path = project_root / "backtest" / "forensic_log.csv"
    df = pl.read_csv(csv_path)
    
    events = ["CPI", "NFP", "PCE", "ISM", "Retail Sales", "Jobless Claims", "FOMC"]
    
    results = []
    
    # Process Aggregate
    t_base, pf_base = calc_metrics(df)
    filtered_df = df.filter((pl.col("rsi_14") < 40) | (pl.col("rsi_14") > 60))
    t_filt, pf_filt = calc_metrics(filtered_df)
    
    diff = pf_filt - pf_base
    status = "UP" if diff > 0 else "DOWN" if diff < 0 else "FLAT"
    results.append(["ALL EVENTS", t_base, f"{pf_base:.2f}", t_filt, f"{pf_filt:.2f}", f"{diff:+.2f} ({status})"])
    
    # Process Each Event
    for ev in events:
        ev_df = df.filter(pl.col("event_category") == ev)
        t_base, pf_base = calc_metrics(ev_df)
        
        ev_filt = ev_df.filter((pl.col("rsi_14") < 40) | (pl.col("rsi_14") > 60))
        t_filt, pf_filt = calc_metrics(ev_filt)
        
        diff = pf_filt - pf_base
        status = "UP" if diff > 0 else "DOWN" if diff < 0 else "FLAT"
        if t_base == 0:
            status = "N/A"
            diff = 0.0
            
        results.append([ev, t_base, f"{pf_base:.2f}", t_filt, f"{pf_filt:.2f}", f"{diff:+.2f} ({status})"])
        
    print(tabulate(results, headers=["Event", "Base Trades", "Base PF", "Filter Trades", "Filter PF", "Change in Edge"]))

if __name__ == "__main__":
    main()

