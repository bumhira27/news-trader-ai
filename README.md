# News Trader AI

> Autonomous XAUUSD M1 News Scalper — C# execution engine with native AI heuristics, built on cTrader.

## Live Deployment Simulation (2024 – 2025)

**Strategy:** Holy Trinity (NFP, CPI, Retail Sales) | **Instrument:** XAUUSD | **Timeframe:** M1
**Starting Capital:** $1,000 | **Compounding:** 1x multiplier added every +$3,000 in total pot profit

| Metric | Value |
|---|---|
| Final Compounded Pot | **$30,249.65** |
| Return on Capital | **+2,925%** |
| Total Trades | 46 |
| Backtest Period | Jan 2024 – Apr 2025 |
| Stop Loss | 300 pips |
| Trailing Trigger | 500 pips |
| Trailing Step | 200 pips |

> **Note on Backtest Rigor:** These results are generated using a conservative minute-by-minute sequential state machine. Intrabar paths strictly assume adverse excursions (Stop Losses) hit *before* favorable ones (Trail Triggers), and trailing stops correctly require full retracement steps to exit. Timestamps are strictly locked to canonical economic calendar releases (e.g. 15:30) to eliminate any look-ahead bias from observed price action.

### Dual-Terminal Asymmetric Straddle Setup
- **Terminal 1 (BiasAccount):** Base Risk **$300** (Trades AI predicted direction)
- **Terminal 2 (HedgeAccount):** Base Risk **$150** (Trades opposite direction)

### Performance by Event

| Event | Trades | Wins | Losses | Win Rate |
|---|---|---|---|---|
| NFP | 16 | 13 | 3 | 81.3% |
| CPI | 15 | 10 | 5 | 66.7% |
| Retail Sales | 15 | 11 | 4 | 73.3% |
| **Overall** | **46** | **34** | **12** | **73.9%** |

### Compounding Milestones

Because the risk is strictly capped to the allocated block ($450 total exposure), the cash reserve absorbs whipsaws, while the open-ended trailing stop rides winning spikes to easily cover the losses and scale into new multiplier brackets.

| Date | Event | Multiplier | Bias Lots | Hedge Lots | Running Pot |
|---|---|---|---|---|---|
| 2024-01-05 | NFP | 1x | 0.75 | 0.38 | **$1,838.50** |
| 2024-04-10 | CPI | 1x | 0.75 | 0.38 | **$2,198.48** |
| 2024-06-12 | CPI | 2x | 1.50 | 0.75 | **$7,055.00** |
| 2024-07-11 | CPI | 3x | 2.25 | 1.12 | **$11,528.92** |
| 2024-08-02 | NFP | 4x | 3.00 | 1.50 | **$17,471.92** |
| 2024-08-15 | Retail Sales | 7x | 5.25 | 2.62 | **$21,109.42** |
| 2024-10-04 | NFP | 6x | 4.50 | 2.25 | **$24,602.92** |
| 2024-11-13 | CPI | 7x | 5.25 | 2.62 | **$24,716.17** |
| 2024-12-06 | NFP | 9x | 6.75 | 3.38 | **$29,165.92** |
| 2025-02-12 | CPI | 8x | 6.00 | 3.00 | **$30,064.86** |
| 2025-03-07 | NFP | 11x | 8.25 | 4.12 | **$32,491.40** |
| 2025-04-04 | NFP | 11x | 8.25 | 4.12 | **$30,249.65** |

> Full simulation code: [`backtest/forensic_dual_sim.py`](backtest/forensic_dual_sim.py)

## Architecture & Design Rationale

News Trader AI is a fully autonomous C# cBot that plugs directly into cTrader. There is no Python dependency at runtime.

### 1. The Risk Model and "The Pot"
The system utilizes a specialized risk isolation model:
- **The Setup:** Instead of risking the full $1,000 pot directly on one trade, we isolate capital into sub-accounts (e.g., $300 in BiasAccount, $150 in HedgeAccount). 
- **Parameter Usage:** The bot's `Risk Percentage = 80%` parameter applies **only to the local sub-account balance**, not the total pot. 
- **Why we do this:** This hard-caps our maximum exposure during a double-whipsaw (both SLs hit) to exactly the allocated capital. The cash reserve is preserved off-chart, while the active terminal uses maximum leverage to generate asymmetrical upside on the winning leg. As the pot grows by $3,000, we simply transfer more capital into the trading terminals to increase the multiplier.

### 2. Why Random Order Splitting is Necessary
The `OrderSplitting` trade logic splits the calculated lot size into a randomized number of smaller orders (between 10 and 20). This is not an execution bug; it is an active **Broker Obfuscation Strategy**. High-frequency news scalping is often flagged by broker algorithms if executed as massive single-block orders. Randomly splitting the total volume helps mask the straddle signature from toxic flow detection systems.

### 3. Sole Reliance on Trailing Stops
The architecture deliberately omits a Take Profit (TP) parameter. The entire strategy relies heavily on the Trailing Stop mechanism. 
- **The Rationale:** Macro news events often trigger multi-hour directional trends. By not capping the upside, the winning leg (either Bias or Hedge) is allowed to run completely unchecked until volatility reverses. This open-ended exit is exactly how a $300 risk position can generate thousands of dollars on a single NFP print.

### 4. M1 Chart Requirement
While the cBot code is event-driven (using `OnTick` and `OnTimer`), it is strictly designed to be deployed on the **XAUUSD M1 chart**. We do not programmatically lock the timeframe to allow for visual flexibility, but deploying this on higher timeframes will delay trailing stop execution loops and invalidate the backtested entry logic.

### 5. Manual News Timing
The strategy intentionally uses manually configured `News Hour` and `News Minute` inputs rather than relying entirely on the ForexFactory API for execution timing. This ensures the bot always has an explicit, user-validated source of truth for the countdown timer, removing the risk of API latency or unexpected calendar shifts milliseconds before the event.

### The Two-Terminal Setup

| Terminal | Account Role | Direction |
|---|---|---|
| Terminal 1 | `BiasAccount` | AI Bias direction (e.g., BUY) |
| Terminal 2 | `HedgeAccount` | Opposite direction (e.g., SELL) |

The Hedge Account covers the scenario where the AI bias is wrong. At least one leg always profits from the news spike.

## Parameters

| Parameter | Default | Description |
|---|---|---|
| News Hour | 15 | Hour of the news event (SAST / UTC+2) |
| News Minute | 30 | Minute of the news event |
| Account Role | BiasAccount | BiasAccount trades AI direction; HedgeAccount trades opposite |
| Stop Loss (pips) | 300 | Hard stop loss in pips |
| Risk Percentage | 80% | Percentage of account balance used to calculate lot size |
| Seconds Before | 3 | Seconds before news time to fire the order |
| Trailing Stop | Yes | Enables trailing stop (sole exit mechanism) |
| Trail Trigger (pips) | 500 | Price distance from entry before trail activates |
| Trail Step (pips) | 200 | How tightly the trail follows price |
| Trade Logic | Single Order | Single / Split / Cap order distribution |

## Quick Start

```
1. Build NewsTraderEA.cs in cTrader Automate
2. Open XAUUSD M1 chart
3. Add algorithm → set News Hour and News Minute to match ForexFactory
4. Set Account Role to BiasAccount on Terminal 1
5. Open second cTrader terminal → set Account Role to HedgeAccount
6. Both bots fire automatically at the configured time
```

## Repository Structure

```
news-trader-ai/
├── src/
│   └── NewsTraderEA.cs          # C# cBot — full autonomous execution engine
├── backtest/
│   ├── trinity_timeline.py      # Base $5k Holy Trinity equity curve
│   └── forensic_dual_sim.py     # Advanced $1k dual-terminal compound simulation
├── reports/
│   ├── trade_history.csv        # Full chronological trade log
│   ├── event_statistics.csv     # Per-event win rates and P&L
│   ├── equity_graph.png         # Equity curve chart
│   └── cTrader_Backtest_Report.html  # Interactive cTrader-format report
└── live_predictor.py            # CLI tool for manual pre-event bias generation
```
