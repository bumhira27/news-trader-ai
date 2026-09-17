# News Trader AI

Autonomous economic-news context engine and algorithmic execution platform.

## Architectural Overview

News Trader AI solves the structural latency and data-integrity challenges of high-frequency macroeconomic event trading. The system isolates factual calendar data ingestion from predictive interpretation and downstream execution. This decoupled architecture allows for deterministic data normalization, zero-latency local querying, and asymmetric straddle execution on the XAUUSD M1 chart without exposing upstream data collection layers to trading execution loops.

## Core Features & Capabilities

- **Idempotent Data Ingestion Pipeline**: Deterministic `source_event_key` hashing ensures zero-duplicate upserts from upstream economic calendar feeds, supporting historical revisions and time-series boundaries.
- **Dynamic Persistence Layer**: Implements automatic runtime fallback from PostgreSQL (production) to local SQLite (development/testing), ensuring uninterrupted API availability.
- **Derived Analytical Context Engine**: Computes normalized economic surprise, forecast deviation, and builds composite precursor histories (e.g., prior CPI/NFP context ahead of FOMC decisions).
- **Asymmetric Straddle Execution Model**: C# cTrader cBot deployed across dual isolated terminals (Bias and Hedge accounts), strictly relying on dynamic trailing stops to harvest multi-hour directional volatility spikes.

## Component & Tech Stack

### Data Layer (Economic Data Server)
- **Database Engine**: PostgreSQL 15 (Production) / SQLite 3 (Fallback)
- **ORM / Query Builder**: SQLAlchemy `^2.0.0`
- **Driver / Connectivity**: psycopg2-binary `^2.9.9`

### API & Application Layer
- **Runtime Environment**: Python 3.12.10
- **Web Framework**: FastAPI `^0.110.0`
- **ASGI Server**: Uvicorn `^0.28.0`
- **Data Validation**: Pydantic `^2.6.0`

### Client & Execution Infrastructure
- **Context Engine Client**: Python 3.12 (Standard Library + Requests `^2.31.0`)
- **Execution Bot**: C# / .NET 6.0 (cTrader Automate API)
- **Testing Suite**: Pytest `^8.0.0`

## Environment Configuration & Quick Start

### Repository Initialization

```bash
git clone https://github.com/bumhira27/news-trader-ai.git
cd news-trader-ai
```

### Server Deployment (Docker)

The production configuration uses Docker Compose to initialize the PostgreSQL volume and the FastAPI service.

```bash
cd economic_data_server
docker compose up -d --build
```

### Local Development (Direct Host)

```bash
# Initialize virtual environment
python -m venv venv
source venv/bin/activate  # Windows: .\venv\Scripts\activate

# Install component dependencies
pip install -r economic_data_server/requirements.txt
pip install -r requirements.txt

# Start API Server (Defaults to SQLite if Postgres is unreachable)
cd economic_data_server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Database Seeding & Ingestion

Run the ingestion CLI to seed the database with the latest economic calendar events or historical fixtures.

```bash
# Ingest current week's live data
python -m app.ingest --latest

# Ingest historical fixture dataset
python -m app.ingest --file fixtures/forexfactory_2026_08.json
```

## Core API / Integration Contracts

### REST API JSON Payload (`GET /api/v1/events`)

The API exposes normalized economic events mapped to ISO-8601 UTC formats.

**Request:**
```http
GET /api/v1/events?currency=USD&impact=High&limit=1 HTTP/1.1
Host: localhost:8000
```

**Response:**
```json
[
  {
    "id": 142,
    "source_event_key": "ff|2026-08-07T12:30:00+00:00|USD|Nonfarm Payrolls",
    "provider": "forexfactory",
    "timestamp_utc": "2026-08-07T12:30:00Z",
    "currency": "USD",
    "event": "Nonfarm Payrolls",
    "impact": "High",
    "actual": "165K",
    "forecast": "150K",
    "previous": "143K",
    "revised_previous": null
  }
]
```

### Context Engine Integration (Python SDK)

The `ContextEngine` acts as the primary analytical interface for the live predictor.

```python
from data.context_engine import ContextEngine
from datetime import datetime, timezone

engine = ContextEngine(api_base_url="http://localhost:8000/api/v1")

# Fetch recent NFP release for context
target_dt = datetime(2026, 8, 10, tzinfo=timezone.utc)
release = engine.get_latest_release("Nonfarm Payrolls", target_dt)

if release:
    print(f"Surprise vs Forecast: {release['surprise']}")
```

### CLI Predictor Execution

The pre-event analysis tool queries the context engine and generates a bias signal for the C# execution bot.

```bash
python live_predictor.py

# Expected Output:
# === News Trader AI : Live Autonomous Predictor ===
# Fetching live events from Economic Data API...
# [TARGET LOCKED]: Core CPI m/m @ 2026-08-12 12:30:00
# [RESULT] Directional Bias Calculated: BUY (Score: 1.0)
# Bias successfully written to C:\news_bias.txt
```
