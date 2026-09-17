# News Trader AI

## Architectural Overview

News Trader AI is an algorithmic trading execution pipeline engineered to trade high-impact macroeconomic events via the cTrader platform. The primary problem solved is the latency and analytical constraint of processing unstructured macroeconomic calendar data at the moment of release. 

By physically decoupling the data ingestion, context evaluation, and trade execution into isolated layers, this architecture ensures that the execution bot operates purely as a high-speed state machine. It removes expensive XML parsing and heuristic string-matching from the C# runtime, shifting all historical context computation to a dedicated Python backend.

**Value Proposition:** Provides quantitative developers with a deterministic, testable data foundation (Economic Data Server) and an auditable decision engine (Context API), preventing the execution layer from failing due to external API rate limits, missing precursors, or complex timezone shifts.

### Trading Strategy

The system trades directional bias on major macroeconomic releases (such as NFP, CPI, FOMC, and GDP) by evaluating specific historical precursor events. 

1. **Precursor Heuristics:** Before a target event, the Context Engine identifies a highly correlated precursor (e.g., evaluating *ADP Non-Farm Employment* prior to the *Non-Farm Payrolls* release).
2. **Surprise Scoring:** It calculates the "surprise" of the precursor (Actual - Forecast) and applies an asset-specific weight (e.g., a strong US employment precursor acts as a negative weight on USD-denominated assets like XAUUSD).
3. **Directional Execution:** The evaluated score translates strictly into a `BUY`, `SELL`, or `SKIP` decision.
4. **Risk & Trade Management:** The C# execution client dynamically sizes the position based on account equity and risk parameters. It supports order splitting to optimize fill rates and manages risk dynamically using absolute trailing stops and hard margin limits.

## Core Features & Capabilities

- **Deterministic Time Normalization:** Utilizes IANA timezone mapping (`tzdata`) rather than fixed UTC offsets, guaranteeing correct alignment of historical events across Daylight Saving Time boundaries.
- **Idempotent Data Ingestion:** The data pipeline handles batch processing of historical Forex Factory HTML calendars and current-week XML feeds with automatic duplicate resolution and constraint validation.
- **Decoupled Precursor Heuristics:** Bias evaluation is executed entirely server-side, allowing the engine to scan months of historical data instantly without restricting logic to the current week's feed.
- **Fail-Safe Execution:** The C# client is designed to degrade gracefully. If the Context API times out or returns a 500, the cBot explicitly defaults to a `SKIP` bias, halting trade execution rather than guessing.

## Component & Tech Stack

### Data Layer
- **PostgreSQL 16:** Production relational store for macro events.
- **SQLite:** In-memory isolation for unit testing.
- **SQLAlchemy 2.0.54:** ORM mapping and migration generation.
- **Pydantic 2.13:** Strict schema validation for data ingestion.

### API Layer
- **FastAPI 0.141:** High-performance asynchronous REST API.
- **Uvicorn 0.53:** ASGI web server.
- **BeautifulSoup4 4.15:** Historical HTML parsing for macro calendars.

### Client Infrastructure
- **C# / .NET 6:** cAlgo API trading framework (cTrader).
- **System.Text.Json:** Native JSON deserialization for Context API consumption.

## Environment Configuration & Quick Start

### 1. Repository Setup & Dependencies
```bash
git clone https://github.com/bumhira27/news-trader-ai.git
cd news-trader-ai
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r economic_data_server/requirements.txt
pip install tzdata
```

### 2. Database Initialization
By default, the server will utilize an SQLite database for local development if PostgreSQL credentials are not provided.
```bash
# Optional: Set PostgreSQL credentials
export DATABASE_URL="postgresql://user:password@localhost:5432/economic_data"
```

### 3. Service Initialization
The architecture requires two distinct API services.

**Start the Economic Data Server (Port 8000):**
```bash
cd economic_data_server
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

**Start the Context Engine API (Port 8001):**
```bash
# In a new terminal
python run_context_api.py
```

### 4. Run Test Suite
```bash
# Ensure you are at the repository root
python -m pytest -v
```

## Core API / Integration Contracts

### Context Engine Decision Payload
The C# cBot executes an HTTP `GET` request to the Context API prior to the news event.

**Request:**
```http
GET /api/v1/decision?target_time=2026-09-18T14:30:00Z&symbol=USD HTTP/1.1
Host: 127.0.0.1:8001
```

**Response (200 OK):**
```json
{
  "decision": "BUY",
  "event": "Non-Farm Employment Change",
  "event_timestamp": "2026-09-18T14:30:00+00:00",
  "currency": "USD",
  "facts_used": 1,
  "context": {
    "precursor_event": "ADP Non-Farm Employment Change",
    "actual": 143000.0,
    "forecast": 120000.0,
    "previous": 105000.0
  },
  "reason": "Precursor 'ADP Non-Farm Employment Change' surprise=23000.0 * weight=-1.5 -> score=-34500.0",
  "valid_until": "2026-09-18T14:35:00+00:00"
}
```
