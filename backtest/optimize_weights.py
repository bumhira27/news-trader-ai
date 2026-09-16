import sys
from pathlib import Path
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data.load_prices import load_xauusd_prices
from backtest.event_backtest import filter_target_events, map_event_category, _attach_mfe_mae

def compute_technicals(prices: pl.DataFrame) -> pl.DataFrame:
    prices = prices.with_columns([
        pl.col("close").rolling_mean(window_size=200).alias("sma_200"),
    ])
    delta = pl.col("close").diff()
    up = pl.when(delta > 0).then(delta).otherwise(0.0)
    down = pl.when(delta < 0).then(-delta).otherwise(0.0)
    avg_up = up.rolling_mean(window_size=14)
    avg_down = down.rolling_mean(window_size=14)
    rs = avg_up / avg_down
    prices = prices.with_columns((100 - (100 / (1 + rs))).alias("rsi_14"))
    return prices

def custom_scorecard(row, weights):
    # weights: dict with keys like event_wt, yield_wt, yield_hi, yield_lo
    score = 0.0
    forecast = row.get("forecast")
    previous = row.get("previous")
    event_name = row.get("event", "").lower()
    
    if forecast is None or previous is None:
        return 0.0, "SKIP"
        
    # Event logic
    strong = forecast > previous
    weak = forecast < previous
    
    if "non-farm" in event_name:
        if strong: score -= weights["labor_wt"]
        elif weak: score += weights["labor_wt"]
    elif "ism" in event_name or "retail" in event_name:
        if strong: score -= weights["growth_wt"]
        elif weak: score += weights["growth_wt"]
        
    # Macro logic
    us10y = row.get("us10y_yield")
    if us10y is not None:
        if us10y > weights["yield_hi"]: score -= weights["yield_wt"]
        elif us10y < weights["yield_lo"]: score += weights["yield_wt"]
        
    score += 0.5 # safe haven constant
    
    bias = "BUY" if score > weights["threshold"] else "SELL" if score < -weights["threshold"] else "SKIP"
    return score, bias

def evaluate_params(aligned: pl.DataFrame, prices: pl.DataFrame, weights: dict):
    rows = aligned.to_dicts()
    for row in rows:
        score, bias = custom_scorecard(row, weights)
        row["scorecard_total"] = score
        row["predicted_direction"] = bias
        
    df = pl.DataFrame(rows).filter(pl.col("predicted_direction") != "SKIP")
    
    if df.height == 0:
        return {"pf_nfp": 0.0, "pf_ret": 0.0, "pf_ism": 0.0, "pf_total": 0.0, "trades": 0}
        
    df = _attach_mfe_mae(df, prices)
    df = df.with_columns(
        pl.col("event").map_elements(map_event_category, return_dtype=pl.Utf8).alias("event_category")
    )
    
    # Evaluate Portfolio
    # NFP (Unfiltered)
    nfp = df.filter(pl.col("event_category") == "NFP")
    pf_nfp = (nfp["mfe_30m"].sum() / nfp["mae_30m"].sum()) if nfp.height > 0 and nfp["mae_30m"].sum() > 0 else 0.0
    
    # Retail Sales (Unfiltered)
    ret = df.filter(pl.col("event_category") == "Retail Sales")
    pf_ret = (ret["mfe_30m"].sum() / ret["mae_30m"].sum()) if ret.height > 0 and ret["mae_30m"].sum() > 0 else 0.0
    
    # ISM (Filtered: RSI < 40 or > 60)
    ism = df.filter((pl.col("event_category") == "ISM") & ((pl.col("rsi_14") < 40) | (pl.col("rsi_14") > 60)))
    pf_ism = (ism["mfe_30m"].sum() / ism["mae_30m"].sum()) if ism.height > 0 and ism["mae_30m"].sum() > 0 else 0.0
    
    # Total Portfolio score
    pf_total = (pf_nfp + pf_ret + pf_ism) / 3.0
    return {"pf_nfp": pf_nfp, "pf_ret": pf_ret, "pf_ism": pf_ism, "pf_total": pf_total, "trades": nfp.height + ret.height + ism.height}

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
    
    # Base Weights
    base_weights = {"labor_wt": 1.0, "growth_wt": 1.0, "yield_wt": 1.0, "yield_hi": 4.5, "yield_lo": 3.8, "threshold": 1.0}
    base_res = evaluate_params(aligned, prices, base_weights)
    print(f"BASELINE: NFP: {base_res['pf_nfp']:.2f} | Retail: {base_res['pf_ret']:.2f} | ISM (Filt): {base_res['pf_ism']:.2f} | Overall: {base_res['pf_total']:.2f}")

    best_score = base_res["pf_total"]
    best_weights = base_weights
    
    # Grid Search
    print("Optimizing weights...")
    for lw in [1.0, 1.5, 2.0]:
        for gw in [1.0, 1.5, 2.0]:
            for yw in [0.5, 1.0, 1.5]:
                for yhi in [4.2, 4.5]:
                    for ylo in [3.8, 4.0]:
                        for th in [1.0, 1.5]:
                            w = {"labor_wt": lw, "growth_wt": gw, "yield_wt": yw, "yield_hi": yhi, "yield_lo": ylo, "threshold": th}
                            res = evaluate_params(aligned, prices, w)
                            if res["pf_total"] > best_score:
                                best_score = res["pf_total"]
                                best_weights = w
                                print(f"NEW BEST: {w} -> {res['pf_total']:.2f} (Trades: {res['trades']})")

    print(f"\nOPTIMIZED RESULT:")
    res = evaluate_params(aligned, prices, best_weights)
    print(f"Weights: {best_weights}")
    print(f"NFP PF: {res['pf_nfp']:.2f}")
    print(f"Retail PF: {res['pf_ret']:.2f}")
    print(f"ISM PF: {res['pf_ism']:.2f}")

if __name__ == "__main__":
    main()
