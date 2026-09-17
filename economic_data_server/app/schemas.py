from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, ConfigDict, field_serializer

class EconomicEventBase(BaseModel):
    source: str = "forexfactory"
    source_event_key: str
    event: str
    event_type: Optional[str] = None
    currency: str
    impact: str
    timestamp_utc: datetime
    actual: Optional[str] = None
    forecast: Optional[str] = None
    previous: Optional[str] = None
    detail_url: Optional[str] = None
    source_url: Optional[str] = None

class EconomicEventCreate(EconomicEventBase):
    pass

class EconomicEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    source_event_key: str
    event: str
    event_type: Optional[str] = None
    currency: str
    impact: str
    timestamp_utc: datetime
    actual: Optional[str] = None
    forecast: Optional[str] = None
    previous: Optional[str] = None
    detail_url: Optional[str] = None

    @field_serializer("timestamp_utc")
    def serialize_timestamp(self, dt: datetime, _info):
        # Canonical UTC ISO-8601 string ending in Z
        if dt.tzinfo is None:
            return dt.isoformat() + "Z"
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

class IngestionRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    started_at: datetime
    finished_at: Optional[datetime] = None
    source: str
    requested_start: Optional[str] = None
    requested_end: Optional[str] = None
    records_found: int
    records_inserted: int
    records_updated: int
    records_rejected: int
    status: str
    error_message: Optional[str] = None

class ValidationReport(BaseModel):
    total_records: int
    unique_records: int
    duplicate_records: int
    missing_timestamps: int
    missing_currencies: int
    missing_event_names: int
    missing_actual: int
    missing_forecast: int
    missing_previous: int
    records_by_currency: Dict[str, int]
    records_by_impact: Dict[str, int]

class HealthResponse(BaseModel):
    status: str
    service: str
    database: str
    version: str = "1.0.0"
