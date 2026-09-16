import sys
from pathlib import Path
import polars as pl
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data.load_prices import load_xauusd_prices
from backtest.event_backtest import filter_target_events, map_event_category, _compute_mfe_mae_for_row

def compute_technicals(prices: pl.DataFrame) -> pl.DataFrame:
    delta = pl.col("close").diff()
    up = pl.when(delta > 0).then(delta).otherwise(0.0)
    down = pl.when(delta < 0).then(-delta).otherwise(0.0)
    avg_up = up.rolling_mean(window_size=14)
    avg_down = down.rolling_mean(window_size=14)
    rs = avg_up / avg_down
    prices = prices.with_columns((100 - (100 / (1 + rs))).alias("rsi_14"))
    return prices

def custom_scorecard(row, weights):
    score = 0.0
    forecast = row.get("forecast")
    previous = row.get("previous")
    event_name = row.get("event", "").lower()
    if forecast is None or previous is None: return 0.0, "SKIP"
    strong = forecast > previous
    weak = forecast < previous
    if "non-farm" in event_name:
        if strong: score -= weights["labor_wt"]
        elif weak: score += weights["labor_wt"]
    elif "ism" in event_name or "retail" in event_name:
        if strong: score -= weights["growth_wt"]
        elif weak: score += weights["growth_wt"]
    us10y = row.get("us10y_yield")
    if us10y is not None:
        if us10y > weights["yield_hi"]: score -= weights["yield_wt"]
        elif us10y < weights["yield_lo"]: score += weights["yield_wt"]
    score += 0.5 
    bias = "BUY" if score >= weights["threshold"] else "SELL" if score <= -weights["threshold"] else "SKIP"
    return score, bias

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
    aligned = aligned.with_columns(
        pl.col("event").map_elements(map_event_category, return_dtype=pl.Utf8).alias("event_category")
    )
    
    # Precompute BUY and SELL excursions for every row
    print("Precomputing excursions...")
    rows = aligned.to_dicts()
    for row in rows:
        row["predicted_direction"] = "BUY"
        buy_res = _compute_mfe_mae_for_row(row, prices)
        row["buy_mfe_30m"] = buy_res["mfe_30m"]
        row["buy_mae_30m"] = buy_res["mae_30m"]
        
        row["predicted_direction"] = "SELL"
        sell_res = _compute_mfe_mae_for_row(row, prices)
        row["sell_mfe_30m"] = sell_res["mfe_30m"]
        row["sell_mae_30m"] = sell_res["mae_30m"]
        
    print("Optimizing...")
    best_score = 0
    best_weights = None
    
    base_w = {"labor_wt": 1.0, "growth_wt": 1.0, "yield_wt": 1.0, "yield_hi": 4.5, "yield_lo": 3.8, "threshold": 1.0}
    
    # Evaluate a configuration
    def eval_config(w):
        mfe_nfp = mae_nfp = mfe_ret = mae_ret = mfe_ism = mae_ism = 0.0
        n_nfp = n_ret = n_ism = 0
        for r in rows:
            cat = r["event_category"]
            if cat not in ["NFP", "Retail Sales", "ISM"]: continue
            score, bias = custom_scorecard(r, w)
            if bias == "SKIP": continue
            
            mfe = r["buy_mfe_30m"] if bias == "BUY" else r["sell_mfe_30m"]
            mae = r["buy_mae_30m"] if bias == "BUY" else r["sell_mae_30m"]
            if mfe is None or mae is None: continue
            
            if cat == "NFP":
                mfe_nfp += mfe; mae_nfp += mae; n_nfp += 1
            elif cat == "Retail Sales":
                mfe_ret += mfe; mae_ret += mae; n_ret += 1
            elif cat == "ISM":
                rsi = r.get("rsi_14")
                if rsi is not None and (rsi < 40 or rsi > 60):
                    mfe_ism += mfe; mae_ism += mae; n_ism += 1
                    
        pf_nfp = (mfe_nfp / mae_nfp) if mae_nfp > 0 else 0
        pf_ret = (mfe_ret / mae_ret) if mae_ret > 0 else 0
        pf_ism = (mfe_ism / mae_ism) if mae_ism > 0 else 0
        return (pf_nfp + pf_ret + pf_ism) / 3.0, pf_nfp, pf_ret, pf_ism, n_nfp, n_ret, n_ism

    base_score, bn, br, bi, tn, tr, ti = eval_config(base_w)
    print(f"BASELINE: NFP: {bn:.2f} ({tn} trades), Retail: {br:.2f} ({tr} trades), ISM: {bi:.2f} ({ti} trades) | Avg PF: {base_score:.2f}")
    
    for lw in [1.0, 1.5, 2.0]:
        for gw in [1.0, 1.5, 2.0]:
            for yw in [0.5, 1.0, 1.5]:
                for yhi in [4.2, 4.5]:
                    for ylo in [3.8, 4.0]:
                        for th in [1.0, 1.5]:
                            w = {"labor_wt": lw, "growth_wt": gw, "yield_wt": yw, "yield_hi": yhi, "yield_lo": ylo, "threshold": th}
                            score, sn, sr, si, tnn, tnr, tni = eval_config(w)
                            if score > best_score:
                                best_score = score
                                best_weights = w
    
    print("\nOPTIMIZED WEIGHTS:")
    print(best_weights)
    _, sn, sr, si, tnn, tnr, tni = eval_config(best_weights)
    print(f"NEW NFP: PF {sn:.2f} (Trades: {tnn})")
    print(f"NEW Retail: PF {sr:.2f} (Trades: {tnr})")
    print(f"NEW ISM: PF {si:.2f} (Trades: {tni})")
    print(f"NEW Avg PF: {best_score:.2f}")

if __name__ == "__main__":
    main()
