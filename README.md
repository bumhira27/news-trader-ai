# News Trader AI

News Trader AI is the interpretation layer for an economic-news trading system. The repository now keeps the data layer deliberately small: Forex Factory supplies calendar facts, the Economic Data Server stores and serves them, and the downstream trading logic interprets those facts.

## Current architecture

```text
Forex Factory
   │
   ├─ current week export
   └─ historical month calendar
   │
   ▼
Economic Data Server
   ├─ ingestion
   ├─ normalization
   ├─ validation
   ├─ PostgreSQL
   └─ FastAPI
   │
   ▼
News Trader AI Context Engine
   ├─ historical release lookup
   ├─ surprise calculations
   └─ event context
   │
   ▼
cTrader execution bot
```

The Economic Data Server stores economic-calendar facts. It does not store XAUUSD reaction data, MFE/MAE, tick-price research, or machine-learning datasets.

## Repository structure

```text
news-trader-ai/
├── economic_data_server/
│   ├── app/
│   │   ├── main.py
│   │   ├── db.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── ingest.py
│   │   ├── normalizer.py
│   │   ├── validator.py
│   │   └── providers/
│   │       ├── base.py
│   │       └── forexfactory.py
│   ├── fixtures/
│   │   └── forexfactory_2026_08.json
│   ├── tests/
│   │   ├── test_api.py
│   │   ├── test_forexfactory_provider.py
│   │   ├── test_ingest.py
│   │   ├── test_normalizer.py
│   │   └── test_validator.py
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── requirements.txt
│   └── README.md
├── data/
│   └── context_engine.py
├── scoring/
├── src/
│   └── NewsTraderEA.cs
├── pyproject.toml
└── requirements.txt
```

## Economic Data Server

The server uses PostgreSQL explicitly. There is no silent PostgreSQL-to-SQLite fallback.

Docker:

```bash
cd economic_data_server
docker compose up -d --build
```

The API runs at `http://localhost:8000`.

Historical month:

```bash
cd economic_data_server
python -m app.ingest --year 2026 --month 8
```

Historical range:

```bash
python -m app.ingest --start 2026-08-01 --end 2026-08-31
```

Current week:

```bash
cd economic_data_server
python -m app.ingest --latest
```

The historical importer retrieves the requested month from Forex Factory's historical calendar rather than treating a checked-in fixture as production data.

## API

`GET /health`

`GET /api/v1/events`

`GET /api/v1/events/{id}`

`GET /api/v1/calendar/{year}/{month}`

`GET /api/v1/news-events`

`GET /api/v1/ingest/runs`

`GET /api/v1/validation-report`

## Context Engine

`data/context_engine.py` is the analytical client. It queries the Economic Data API and calculates derived metrics such as economic surprise and forecast deviation. Those derived values stay outside the source database.

## Testing

```bash
cd economic_data_server
pytest tests/ -v
```

## Data-source boundary

Forex Factory is the upstream source used by this project. Historical HTML is used for month-level retrieval because the FairEconomy export is a current-week feed. The application does not attempt to bypass access controls or scrape price/reaction data.
