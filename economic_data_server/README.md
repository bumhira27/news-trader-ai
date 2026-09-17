# Economic Data Server

Dedicated economic-calendar context engine and API server for News Trader AI. Supplies normalized, validated historical and current macroeconomic calendar data without trading-reaction calculations or machine-learning dependencies.

## Architecture

```
Forex Factory (Export / HTML)
        │
        ▼
Economic Data Ingestion (app.ingest)
        │
        ▼
Normalization & Validation (app.normalizer, app.validator)
        │
        ▼
PostgreSQL / SQLite (app.models)
        │
        ▼
FastAPI Server (app.main)
        │
        ▼
News Trader AI Context Engine
```

## Directory Structure

```
economic_data_server/
├── app/
│   ├── __init__.py
│   ├── main.py            # FastAPI endpoints and route handlers
│   ├── db.py              # Database session and connection pooling
│   ├── models.py          # SQLAlchemy models (EconomicEvent, IngestionRun, EventRevision)
│   ├── schemas.py         # Pydantic schemas for requests and responses
│   ├── ingest.py          # Ingestion pipeline and CLI runner
│   ├── normalizer.py      # Data cleaning, UTC conversion, and key generator
│   ├── validator.py       # Data validation and duplicate boundary checking
│   └── providers/
│       ├── __init__.py
│       ├── base.py        # Abstract BaseCalendarProvider interface
│       └── forexfactory.py# Forex Factory export and file provider
├── tests/
│   ├── __init__.py
│   ├── test_normalizer.py
│   ├── test_validator.py
│   ├── test_ingest.py
│   └── test_api.py
├── fixtures/
│   └── forexfactory_2026_08.json
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## Running with Docker Compose

To start PostgreSQL and the FastAPI application in containers:

```bash
docker compose up -d --build
```

The server will be reachable at `http://localhost:8000`.

## Running Locally

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Start the FastAPI server:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The database connection defaults to `postgresql://postgres:postgres@localhost:5432/economic_data`. If PostgreSQL is not detected, it automatically uses `sqlite:///./economic_data.db` for local testing.

## Ingestion Commands

Import a specific historical month:

```bash
python -m app.ingest --year 2026 --month 8
```

Import an explicit date window:

```bash
python -m app.ingest --start 2026-08-01 --end 2026-08-31
```

Import the latest releases from the upstream feed:

```bash
python -m app.ingest --latest
```

Import from a local fixture or export file:

```bash
python -m app.ingest --file fixtures/forexfactory_2026_08.json
```

All ingestion operations are idempotent. Repeated executions update modified fields without duplicating rows.

## API Endpoints

Base URL: `http://localhost:8000`

### Health Check
- `GET /health`
  Returns service status and database connectivity.

### Economic Events
- `GET /api/v1/events`
  Filters: `start`, `end`, `currency`, `impact`, `event`, `event_type`, `limit`, `offset`.
  Example:
  `/api/v1/events?currency=USD&impact=High&start=2026-08-01`

### Monthly Calendar
- `GET /api/v1/calendar/{year}/{month}`
  Example:
  `/api/v1/calendar/2026/8`

### Single Event
- `GET /api/v1/events/{id}`
  Example:
  `/api/v1/events/7`

### News-Relevant Context
- `GET /api/v1/news-events?currency=USD&high_impact_only=true`
  Returns high-relevance calendar events for upstream decision engines.

### Validation Report
- `GET /api/v1/validation-report?year=2026&month=8`
  Returns data quality metrics: total records, unique keys, duplicates, and breakdowns by currency and impact.

### Ingestion Runs
- `GET /api/v1/ingest/runs`
  Returns audit logs of recent ingestion jobs with inserted/updated/rejected counts.

## Testing

Run the test suite:

```bash
pytest tests/ -v
```
