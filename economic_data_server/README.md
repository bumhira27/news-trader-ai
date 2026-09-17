# Economic Data Server

Small internal API for News Trader AI economic-calendar data.

## Scope

V1 stores only economic-event data:

- event
- event_type
- currency
- impact
- timestamp_utc
- actual
- forecast
- previous
- source metadata

XAUUSD price reaction, surprise calculations, MFE/MAE, spread, volatility and model features stay in News Trader AI.

## Architecture

Forex Factory -> ingestion/normalization -> PostgreSQL -> FastAPI -> News Trader AI

The Forex Factory scraper reference used for the ingestion design is `ehsanrs2/forexfactory-scraper`. Its useful concepts are provider separation, normalization, historical caching and validation. We are not copying its GPL-3.0 code into this repository.

## Run

From `economic_data_server/`:

```bash
docker compose up --build
```

API: `http://localhost:8000`

Health:

```text
GET /health
```

Events:

```text
GET /api/v1/events?start=2026-08-01&end=2026-09-01&currency=USD
```

Month:

```text
GET /api/v1/calendar/2026/8
```

## Import a historical month

With PostgreSQL available and the Python dependencies installed:

```bash
python -m app.ingest --year 2026 --month 8
```

The importer walks the Forex Factory calendar by week, keeps only events inside the requested month, normalizes release times to UTC and upserts them using a deterministic source key.

## Data model

The public API is intentionally small. News Trader AI should consume the economic data through the API rather than reading scraper output directly.

`event_type` is nullable in V1. We do not invent an event taxonomy when the upstream calendar does not consistently expose one in the visible calendar data.

## Important

Forex Factory currently exposes weekly calendar exports in CSV, JSON, XML and ICS alongside its calendar. Historical coverage and permitted automated use should still be verified against the current Forex Factory terms before production automation or redistribution.
