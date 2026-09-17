# Economic Data Server

Dedicated economic-calendar data service for News Trader AI. It supplies factual calendar records only:

- event
- currency
- impact
- timestamp_utc
- actual
- forecast
- previous
- source/detail metadata

It does not calculate XAUUSD reactions, MFE/MAE, trading outcomes, or machine-learning features.

## Architecture

```text
Forex Factory
   ├─ current week export (JSON/XML)
   └─ historical month calendar (HTML)
              │
              ▼
       Economic Ingestion
              │
              ▼
      Normalize + Validate
              │
              ▼
          PostgreSQL
              │
              ▼
          FastAPI REST
              │
              ▼
      News Trader AI Context Engine
```

The production database is PostgreSQL. SQLite is used only inside tests when a test explicitly provides an SQLite engine. The server never silently switches database engines.

## Run with Docker Compose

```bash
docker compose up -d --build
```

The API will be available at `http://localhost:8000`.

## Local Setup

Set PostgreSQL explicitly:

```bash
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/economic_data"
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

On Windows PowerShell:

```powershell
$env:DATABASE_URL="postgresql://postgres:postgres@localhost:5432/economic_data"
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Ingestion

Historical month. This retrieves the requested month directly from Forex Factory's historical calendar page rather than automatically substituting a local fixture:

```bash
python -m app.ingest --year 2026 --month 8
```

Explicit historical range:

```bash
python -m app.ingest --start 2026-08-01 --end 2026-08-31
```

Current release feed:

```bash
python -m app.ingest --latest
```

Explicit local file. This is intended for deterministic tests or controlled imports only:

```bash
python -m app.ingest --file fixtures/forexfactory_2026_08.json
```

All writes use a deterministic `source_event_key`, so repeated ingestion is idempotent and revised actual/forecast/previous values are tracked in `event_revisions`.

## API

Base URL: `http://localhost:8000`

`GET /health`  
Database/service health.

`GET /api/v1/events`  
Filters: `start`, `end`, `currency`, `impact`, `event`, `event_type`, `limit`, `offset`.

Example:

```text
/api/v1/events?currency=USD&impact=High&start=2026-08-01&end=2026-08-31
```

`GET /api/v1/calendar/{year}/{month}`  
Full monthly calendar view.

`GET /api/v1/events/{id}`  
Single event lookup.

`GET /api/v1/news-events?currency=USD&high_impact_only=true`  
Factual filtered view for downstream context logic. It does not make trading decisions.

`GET /api/v1/ingest/runs`  
Recent ingestion audit records.

`GET /api/v1/validation-report?year=2026&month=8`  
Data-quality report.

## Testing

```bash
pytest tests/ -v
```
