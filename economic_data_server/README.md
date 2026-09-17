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

```bash
docker compose up --build
```

API: `http://localhost:8000`

Health: `GET /health`

Events: `GET /api/v1/events?start=2026-08-01&end=2026-09-01&currency=USD`

Month: `GET /api/v1/calendar/2026/8`

## Important

Forex Factory data access/export availability and permitted use should be verified against the current Forex Factory terms before production automation or redistribution.
