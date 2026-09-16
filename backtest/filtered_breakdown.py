import polars as pl
from pathlib import Path

def main():
    project_root = Path(__file__).resolve().parent.parent
    csv_path = project_root / "backtest" / "forensic_log.csv"
    
    if not csv_path.exists():
        print("forensic_log.csv not found!")
        return
        
    df = pl.read_csv(csv_path)
    
    # Define filters
    # Filter 1: RSI Extreme (<40 or >60)
    df_filtered = df.filter((pl.col("rsi_14") < 40) | (pl.col("rsi_14") > 60))
    
    def summarize(data: pl.DataFrame, label: str):
        n = data.height
        if n == 0:
            return {"Event": label, "Trades": 0, "Avg MFE": 0.0, "Avg MAE": 0.0, "Profit Factor": 0.0}
        avg_mfe = data["mfe_30m"].drop_nulls().mean() or 0.0
        avg_mae = data["mae_30m"].drop_nulls().mean() or 0.0
        pf = (avg_mfe / avg_mae) if avg_mae > 0 else 0.0
        return {"Event": label, "Trades": n, "Avg MFE": round(avg_mfe, 2), "Avg MAE": round(avg_mae, 2), "Profit Factor": round(pf, 2)}
        
    print("========== RSI-FILTERED RESULTS PER EVENT ==========")
    print("Only trading when RSI > 60 or RSI < 40 (Coiled Market)")
    print("-" * 50)
    
    summary_all = summarize(df_filtered, "ALL TARGET EVENTS (Agg)")
    print(f"{summary_all['Event']:<25} | Trades: {summary_all['Trades']:<3} | Avg MFE: ${summary_all['Avg MFE']:<5.2f} | Avg MAE: ${summary_all['Avg MAE']:<5.2f} | PF: {summary_all['Profit Factor']:.2f}")
    
    # Adding CPI back for visibility (though we recommend excluding it)
    # The forensic_log.csv excluded CPI. Let's run it on the events in the log.
    for cat in ["NFP", "PCE", "ISM", "Retail Sales", "Jobless Claims", "FOMC"]:
        cat_df = df_filtered.filter(pl.col("event_category") == cat)
        if cat_df.height > 0:
            s = summarize(cat_df, f"  -> {cat}")
            print(f"{s['Event']:<25} | Trades: {s['Trades']:<3} | Avg MFE: ${s['Avg MFE']:<5.2f} | Avg MAE: ${s['Avg MAE']:<5.2f} | PF: {s['Profit Factor']:.2f}")

if __name__ == "__main__":
    main()
