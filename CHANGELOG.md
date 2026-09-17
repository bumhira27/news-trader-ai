# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0-rc] - 2026-09-17

### Added
- Context Engine API service running on port 8001 to serve trade bias decisions.
- Centralized `evaluate_bias()` logic in the Python layer to handle all NFP, CPI, FOMC, and GDP precursor heuristics.
- Structured JSON contract for Context API responses, providing `decision`, `facts_used`, `reason`, and detailed `context`.
- Dedicated SQLite test isolation overriding PostgreSQL during `pytest` runs.
- IANA-aware timezone normalizer relying on `tzdata` to correctly parse historical DST boundaries (e.g., `America/New_York`).
- HTML parser in `ForexFactoryProvider` for accurate historical calendar scraping.

### Changed
- C# cBot (`NewsTraderEA.cs`) refactored from a standalone scraper to a stateless execution client.
- `ContextEngine` now supports broad temporal event lookups instead of being restricted to the current week's XML feed.
- Moved Python dependencies to a strictly defined `economic_data_server/requirements.txt`.

### Fixed
- Replaced hardcoded `-4` hour UTC offsets with programmatic DST handling.
- C# bot now gracefully defaults to `SKIP` (No Trade) if the Context Engine API is unreachable or returns a 500 error.
- Eliminated silent fallback from PostgreSQL to SQLite in production paths.

### Removed
- Legacy machine learning research artifacts (`scorecard.parquet`, `surprise_direction.parquet`).
- `live_predictor.py` and `news_bias.txt` IPC architecture.
- Deprecated dependency chain (Removed `polars`, `pyarrow`, `scikit-learn`, `plotly`, `kaleido`, `datasets`).
- Direct `ff_calendar_thisweek.xml` feed processing and XML deserialization inside the C# cBot.
- Synthetic fixture generators from production repository.
