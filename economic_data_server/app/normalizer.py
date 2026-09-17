import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Any, Dict

def normalize_raw_value(val: Any) -> Optional[str]:
    """Preserve raw economic string representation while trimming whitespace."""
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "null", "-", "--"):
        return None
    return s

def normalize_currency(curr: Any) -> str:
    """Normalize currency to clean uppercase code."""
    if not curr:
        return "USD"
    c = str(curr).strip().upper()
    return c if c else "USD"

def normalize_impact(impact_str: Any) -> str:
    """Standardize impact string into High, Medium, Low, or Non-Economic."""
    if not impact_str:
        return "Low"
    s = str(impact_str).strip().lower()
    if "high" in s:
        return "High"
    if "medium" in s or "med" in s:
        return "Medium"
    if "low" in s:
        return "Low"
    if "holiday" in s or "non" in s:
        return "Non-Economic"
    return "Low"

def normalize_event_name(name: Any) -> str:
    """Clean extra spaces while preserving original event naming."""
    if not name:
        return ""
    return " ".join(str(name).strip().split())

def parse_iso_datetime(dt_str: str) -> datetime:
    """Parse ISO datetime and convert strictly to UTC."""
    dt_str = dt_str.strip()
    if dt_str.endswith("Z"):
        dt_str = dt_str[:-1] + "+00:00"
    dt = datetime.fromisoformat(dt_str)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def parse_date_time_components(date_str: str, time_str: Optional[str] = None, source_tz_offset_hours: int = -4) -> datetime:
    """
    Parse date/time components (e.g., MM-DD-YYYY or YYYY-MM-DD, and 8:30am or 12:30pm).
    Forex Factory FairEconomy exports are by default Eastern Time (UTC-4 in Daylight Saving, UTC-5 in Standard).
    """
    date_str = date_str.strip()
    time_str = (time_str or "").strip()

    # Determine date pattern
    if "-" in date_str:
        parts = date_str.split("-")
        if len(parts[0]) == 4: # YYYY-MM-DD
            year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        else: # MM-DD-YYYY
            month, day, year = int(parts[0]), int(parts[1]), int(parts[2])
    elif "/" in date_str:
        parts = date_str.split("/")
        if len(parts[0]) == 4:
            year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        else:
            month, day, year = int(parts[0]), int(parts[1]), int(parts[2])
    else:
        raise ValueError(f"Unrecognized date format: {date_str}")

    hour, minute = 0, 0
    if time_str and time_str.lower() not in ("all day", "tentative", "day 1", "day 2", "day 3", "none", ""):
        m = re.match(r"^(\d{1,2}):(\d{2})\s*([ap]m)?$", time_str.lower())
        if m:
            h = int(m.group(1))
            minute = int(m.group(2))
            meridiem = m.group(3)
            if meridiem == "pm" and h < 12:
                hour = h + 12
            elif meridiem == "am" and h == 12:
                hour = 0
            else:
                hour = h

    # Source tz (default Eastern -4 hours if not specified)
    tz = timezone(timedelta(hours=source_tz_offset_hours))
    local_dt = datetime(year, month, day, hour, minute, tzinfo=tz)
    return local_dt.astimezone(timezone.utc)

def normalize_timestamp(raw_date: Any, raw_time: Optional[Any] = None) -> datetime:
    """Unified timestamp normalizer returning a UTC timezone-aware datetime."""
    if isinstance(raw_date, datetime):
        if raw_date.tzinfo is None:
            return raw_date.replace(tzinfo=timezone.utc)
        return raw_date.astimezone(timezone.utc)

    s_date = str(raw_date).strip()
    s_time = str(raw_time).strip() if raw_time is not None else ""

    # Check if s_date is already an ISO datetime string
    if "T" in s_date or (len(s_date) >= 19 and " " in s_date and "-" in s_date):
        try:
            return parse_iso_datetime(s_date)
        except Exception:
            pass

    return parse_date_time_components(s_date, s_time)

def build_source_event_key(source: str, timestamp_utc: datetime, currency: str, event_name: str) -> str:
    """Build deterministic unique event key preventing repeated insertions."""
    ts_str = timestamp_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    clean_event = normalize_event_name(event_name)
    clean_curr = normalize_currency(currency)
    return f"{source.lower()}|{ts_str}|{clean_curr}|{clean_event}"

def normalize_event_record(raw: Dict[str, Any], source: str = "forexfactory") -> Dict[str, Any]:
    """Normalize a raw record from any Forex Factory source format."""
    # Field resolution across different provider formats (JSON, XML, CSV, internal)
    raw_title = raw.get("title") or raw.get("event") or raw.get("Event") or raw.get("name")
    raw_currency = raw.get("currency") or raw.get("country") or raw.get("Country") or raw.get("Currency")
    raw_impact = raw.get("impact") or raw.get("Impact")
    raw_date = raw.get("date") or raw.get("DateTime") or raw.get("datetime") or raw.get("Date") or raw.get("timestamp")
    raw_time = raw.get("time") or raw.get("Time")
    raw_actual = raw.get("actual") or raw.get("Actual")
    raw_forecast = raw.get("forecast") or raw.get("Forecast")
    raw_previous = raw.get("previous") or raw.get("Previous")
    raw_url = raw.get("url") or raw.get("detail_url") or raw.get("Detail") or raw.get("URL")

    event_name = normalize_event_name(raw_title)
    currency = normalize_currency(raw_currency)
    impact = normalize_impact(raw_impact)
    timestamp_utc = normalize_timestamp(raw_date, raw_time)

    source_key = build_source_event_key(source, timestamp_utc, currency, event_name)

    return {
        "source": source,
        "source_event_key": source_key,
        "event": event_name,
        "event_type": raw.get("event_type"),
        "currency": currency,
        "impact": impact,
        "timestamp_utc": timestamp_utc,
        "actual": normalize_raw_value(raw_actual),
        "forecast": normalize_raw_value(raw_forecast),
        "previous": normalize_raw_value(raw_previous),
        "detail_url": str(raw_url).strip() if raw_url else None,
        "source_url": raw.get("source_url")
    }
