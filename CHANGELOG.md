# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0-stable] - 2026-09-17

### Added
- **Economic Data Server**: Deployed a dedicated FastAPI microservice to ingest, normalize, and serve macroeconomic calendar events over REST.
- **Persistence Layer**: Implemented PostgreSQL 15 database storage with a dynamic local fallback to SQLite 3 for offline development.
- **Idempotent Ingestion CLI**: Added `app.ingest` module for deterministic upserting of historical fixtures and live XML feeds utilizing composite `source_event_key` hashing.
- **API Contracts**: Introduced `/api/v1/events`, `/api/v1/news-events`, and `/api/v1/validation-report` endpoints for client decoupling.
- **Docker Toolchain**: Included `Dockerfile` and `docker-compose.yml` for isolated data-server execution.
- **Test Infrastructure**: Added a comprehensive `pytest` suite ensuring 100% pass rate across normalizer functions, database validators, API routing, and AI context metrics.

### Changed
- **Architectural Decoupling**: Disconnected the Python analytical stack from downstream price-reaction calculations; isolated execution strictly to the C# cBot interface.
- **Context Engine Logic**: Refactored `data/context_engine.py` to fetch historical precursor events directly from the new Economic Data API instead of local static files.
- **Live Predictor Integration**: Re-wired `live_predictor.py` to route queries through the Context Engine, replacing fragile manual XML polling mechanics.
- **Documentation**: Overhauled `README.md` to document the production-ready microservice architecture and detailed integration payloads.

### Fixed
- **API Polling Resilience**: Resolved immediate crashing in `live_predictor.py` caused by `NoneType` attribute errors during XML ingest by migrating logic to the server-side feed normalizer.
- **Data Validation Failures**: Corrected datetime mapping anomalies by enforcing strictly normalized ISO-8601 UTC formats across all stored events.

### Removed
- **Legacy Machine Learning Pipeline**: Deleted all 32 experimental ML dataset generators, compound simulators, and optimization routines within the `backtest/` directory.
- **Heavy Dependencies**: Pruned `polars`, `pyarrow`, `scikit-learn`, `kaleido`, `plotly`, and `datasets` from project lockfiles to eliminate dead weight and reduce compilation latency.
- **Stale Artifacts**: Removed deprecated HTML backtest reports, equity graph images, and obsolete flat-file JSON databases (`calendar_database.json`).
