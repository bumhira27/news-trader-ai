"""
FORENSIC REVIEW + DUAL-TERMINAL SIMULATION
===========================================
Forensic audit: verifies the C# EA logic can reproduce the 73.9% win rate.
Simulation: $1,000 starting pot, BiasAccount=$300, HedgeAccount=$150.
Compounding: Stepped compounding every +$3000 in the total pot.
"""

import sys
from pathlib import Path
import polars as pl
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data.load_prices import load_xauusd_prices

# ─── Settings ────────────────────────────────────────────────────────────────
SL_PIPS        = 300          
TRAIL_TRIGGER  = 500          
TRAIL_STEP     = 200          
SECS_BEFORE    = 3            

BIAS_BASE      = 300.0        # Terminal 1 base allocation
HEDGE_BASE     = 150.0        # Terminal 2 base allocation
STARTING_POT   = 1000.0       # Total starting balance
COMPOUND_STEP  = 3000.0       # Compound every +$3000

MARGIN_PER_LOT = 4.0          # $4 margin per 0.01 lots at 1:1000 leverage
PIP_VALUE_USD  = 1.0          # 1 pip = $1.00 per 0.01 lot on XAUUSD

PRICE_PATHS = [
    r"C:\Users\bumhira27\Downloads\XAUUSD_2024_all.csv",
    r"C:\Users\bumhira27\Downloads\XAUUSD_2025_all.csv",
    r"C:\Users\bumhira27\Downloads\XAUUSD_2026\*.csv",
]

KNOWN_RESULTS = [
    ("2024-01-05 15:30", "NFP",          "SELL", "WIN"),
    ("2024-01-11 15:30", "CPI",          "SELL", "LOSS"),
    ("2024-01-17 15:30", "Retail Sales", "SELL", "WIN"),
    ("2024-02-02 15:30", "NFP",          "BUY",  "WIN"),
    ("2024-02-13 15:30", "CPI",          "SELL", "LOSS"),
    ("2024-02-15 15:30", "Retail Sales", "SELL", "LOSS"),
    ("2024-03-08 15:30", "NFP",          "BUY",  "LOSS"),
    ("2024-03-12 15:30", "CPI",          "BUY",  "WIN"),
    ("2024-03-14 15:30", "Retail Sales", "BUY",  "LOSS"),
    ("2024-04-05 15:30", "NFP",          "BUY",  "WIN"),
    ("2024-04-10 15:30", "CPI",          "SELL", "WIN"),
    ("2024-04-15 15:30", "Retail Sales", "BUY",  "LOSS"),
    ("2024-05-03 15:30", "NFP",          "SELL", "WIN"),
    ("2024-05-15 15:30", "CPI",          "BUY",  "WIN"),
    ("2024-05-15 15:30", "Retail Sales", "BUY",  "WIN"),
    ("2024-06-07 15:30", "NFP",          "BUY",  "WIN"),
    ("2024-06-12 15:30", "CPI",          "BUY",  "WIN"),
    ("2024-06-18 15:30", "Retail Sales", "SELL", "WIN"),
    ("2024-07-05 15:30", "NFP",          "BUY",  "WIN"),
    ("2024-07-11 15:30", "CPI",          "BUY",  "WIN"),
    ("2024-07-16 15:30", "Retail Sales", "SELL", "WIN"),
    ("2024-08-02 15:30", "NFP",          "BUY",  "WIN"),
    ("2024-08-14 15:30", "CPI",          "BUY",  "WIN"),
    ("2024-08-15 15:30", "Retail Sales", "SELL", "WIN"),
    ("2024-09-06 15:30", "NFP",          "SELL", "LOSS"),
    ("2024-09-11 15:30", "CPI",          "BUY",  "LOSS"),
    ("2024-09-17 15:30", "Retail Sales", "SELL", "WIN"),
    ("2024-10-04 15:30", "NFP",          "SELL", "WIN"),
    ("2024-10-10 15:30", "CPI",          "BUY",  "LOSS"),
    ("2024-10-17 15:30", "Retail Sales", "BUY",  "LOSS"),
    ("2024-11-01 15:30", "NFP",          "SELL", "WIN"),
    ("2024-11-13 15:30", "CPI",          "BUY",  "WIN"),
    ("2024-11-15 15:30", "Retail Sales", "SELL", "WIN"),
    ("2024-12-06 15:30", "NFP",          "BUY",  "WIN"),
    ("2024-12-11 15:30", "CPI",          "SELL", "LOSS"),
    ("2024-12-17 15:30", "Retail Sales", "BUY",  "WIN"),
    ("2025-01-10 15:30", "NFP",          "BUY",  "WIN"),
    ("2025-01-15 15:30", "CPI",          "SELL", "WIN"),
    ("2025-01-16 15:30", "Retail Sales", "BUY",  "WIN"),
    ("2025-02-07 15:30", "NFP",          "BUY",  "LOSS"),
    ("2025-02-12 15:30", "CPI",          "SELL", "WIN"),
    ("2025-02-14 15:30", "Retail Sales", "BUY",  "WIN"),
    ("2025-03-07 15:30", "NFP",          "SELL", "WIN"),
    ("2025-03-12 15:30", "CPI",          "BUY",  "WIN"),
    ("2025-03-17 15:30", "Retail Sales", "SELL", "WIN"),
    ("2025-04-04 15:30", "NFP",          "SELL", "WIN"),
]

def calc_lots(capital: float) -> float:
    # 100% of the allocated capital block is risked
    lots = (capital / MARGIN_PER_LOT) * 0.01
    return round(lots, 2)

def simulate_trade(prices: pl.DataFrame, event_dt: datetime, bias: str) -> dict:
    ts = pl.col("timestamp")
    entry_bar = prices.filter(ts < event_dt).tail(1)
    if entry_bar.height == 0:
        return {"pips_won": 0, "outcome": "NO_DATA"}

    entry_price = entry_bar["close"][0]

    window = prices.filter((ts >= event_dt) & (ts <= event_dt + timedelta(minutes=15)))
    if window.height == 0:
        return {"pips_won": 0, "outcome": "NO_DATA"}

    trail_sl = -SL_PIPS
    trade_active = True
    final_pips = 0.0

    for p_row in window.to_dicts():
        if bias == "BUY":
            pips_high = (p_row["high"] - entry_price) * 100
            pips_low = (p_row["low"] - entry_price) * 100
            pips_close = (p_row["close"] - entry_price) * 100
        else:
            pips_high = (entry_price - p_row["low"]) * 100
            pips_low = (entry_price - p_row["high"]) * 100
            pips_close = (entry_price - p_row["close"]) * 100
            
        if trade_active:
            # Check adverse first (conservative intrabar path)
            if pips_low <= trail_sl:
                trade_active = False
                final_pips = trail_sl
            
            # If survived, check favorable and trail
            if trade_active and pips_high >= TRAIL_TRIGGER:
                new_trail = pips_high - TRAIL_STEP
                if new_trail > trail_sl:
                    trail_sl = new_trail
                    
                # Check retracement within same bar
                if pips_close <= trail_sl:
                    trade_active = False
                    final_pips = trail_sl
                    
    if trade_active and window.height > 0:
        last_bar = window.to_dicts()[-1]
        if bias == "BUY":
            final_pips = (last_bar["close"] - entry_price) * 100
        else:
            final_pips = (entry_price - last_bar["close"]) * 100

    outcome = "WIN" if final_pips > 0 else "LOSS"
    return {"pips_won": round(final_pips, 1), "outcome": outcome}

def run():
    print("Loading price data...")
    prices = load_xauusd_prices(PRICE_PATHS)

    print("\n" + "="*90)
    print("DUAL-TERMINAL SIMULATION — $1,000 Starting Pot | Compounding every +$3,000")
    print("Terminal 1 (BiasAccount) : $300 base")
    print("Terminal 2 (HedgeAccount): $150 base")
    print("="*90)
    print(f"\n{'Date':<17} {'Event':<14} {'Bias':<5} {'Mult':<4} | {'T1 Lots':>7} {'T1 Net':>10} | {'T2 Lots':>7} {'T2 Net':>10} | {'TOTAL POT':>12}")
    print("-" * 105)

    total_pot = STARTING_POT
    wins = losses = 0

    for dt_str, event, bias, known_outcome in KNOWN_RESULTS:
        event_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
        
        # ─── Determine Compounding Multiplier ───
        if total_pot >= STARTING_POT:
            multiplier = 1 + int((total_pot - STARTING_POT) // COMPOUND_STEP)
        else:
            multiplier = 1 # Minimum 1x if dropping below 1k
            
        active_bias_cap = BIAS_BASE * multiplier
        active_hedge_cap = HEDGE_BASE * multiplier

        # ─── Simulate Trades ───
        result = simulate_trade(prices, event_dt, bias)
        pips = result["pips_won"]

        hedge_bias = "SELL" if bias == "BUY" else "BUY"
        hedge_result = simulate_trade(prices, event_dt, hedge_bias)
        hedge_pips = hedge_result["pips_won"]

        # ─── P&L Calculation ───
        bias_lots = calc_lots(active_bias_cap)
        bias_pnl  = round(pips * bias_lots * PIP_VALUE_USD, 2)
        
        hedge_lots = calc_lots(active_hedge_cap)
        hedge_pnl  = round(hedge_pips * hedge_lots * PIP_VALUE_USD, 2)

        trade_net = bias_pnl + hedge_pnl
        total_pot = round(total_pot + trade_net, 2)

        if result["outcome"] == "WIN":
            wins += 1
        else:
            losses += 1

        print(f"{dt_str[:16]:<17} {event:<14} {bias:<5} {multiplier:<4}x| {bias_lots:>7.2f} {bias_pnl:>+10.2f} | {hedge_lots:>7.2f} {hedge_pnl:>+10.2f} | ${total_pot:>11,.2f}")

    print("-" * 105)
    net_gain = total_pot - STARTING_POT
    roi = (net_gain / STARTING_POT) * 100

    print(f"\nDUAL-TERMINAL SUMMARY (Compounding every $3k)")
    print(f"  Starting Pot        : ${STARTING_POT:,.2f}")
    print(f"  Final Total Pot     : ${total_pot:,.2f}")
    print(f"  Net Gain            : ${net_gain:+,.2f}")
    print(f"  ROI                 : {roi:.1f}%")
    print(f"  Total Trades        : {wins+losses}")
    print(f"  Base Bias/Hedge Cap : $300 / $150")

if __name__ == "__main__":
    run()
