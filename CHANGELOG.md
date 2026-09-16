# Changelog

All notable changes to the News Trader AI project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2024-11-20

### Changed
- **Architecture Shift:** Replaced Python `live_predictor.py` IPC architecture with a fully native C# AI heuristic engine. cBot now parses the ForexFactory XML directly.
- **Risk Management:** Shifted from hard-coded $1000/$500 logic to a dynamic `RiskPercentage` parameter designed to be used with isolated sub-account balances (The "Pot" model).
- **Execution Guard:** Removed deterministic `OrderCapStrategy` and fully embraced randomized `OrderSplitting` as a broker-obfuscation tactic.
- **Fail-Safe:** Margin safety check prioritized in `OnTick()` execution loop.
- **AI Logic:** Introduced explicit `NO TRADE` / Skip states if precursor data is missing or returns a neutral score.

### Removed
- Removed `news_bias.txt` flat-file observer logic (no longer needed).
- Removed `OrderCapStrategy`.
- **Automated IPC Protocol**: Zero-latency flat-file bridge allowing C# to read python-generated predictions from `C:\news_bias.txt`.
- **Backtest Generation Suite**: Polars and Plotly implementation for outputting equity curves, trade history, and statistical performance matrix.
- **Holy Trinity Filter**: Automated XML parsing of ForexFactory to restrict execution exclusively to NFP, Retail Sales, and CPI.

### Changed
- Re-architected the baseline `News Trader Pro` into `News Trader AI`, stripping obsolete indicators in favor of quantitative event-driven logic.
- Modified Stop Loss logic to account for worst-case M1 pathing and an audited 50-pip slippage penalty model.

### Fixed
- **Sequence of Returns Risk (SoRR)**: Removed ISM, FOMC, and PCE from the execution pipeline to mathematically eliminate early drawdown risk and preserve compounding velocity.

### Security
- **Margin Isolation**: Implemented strict hard-coded lot size formulas mapped to account risk limits ($1000 Bias / $500 Hedge), preventing runaway leverage scaling on double whipsaws.
