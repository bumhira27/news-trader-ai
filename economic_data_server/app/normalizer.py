import re
from datetime import datetime, timezone
from typing import Optional, Any, Dict
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def normalize_raw_value(val: Any) -> Optional[str]:
    """Preserve the source economic value while trimming whitespace."""
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "null", "-", "--"):
        return None
    return s


def normalize_currency(curr: Any) -> str:
    """Normalize currency to a clean uppercase code."""
    if not curr:
        return "USD"
    c = str(curr).strip().upper()
    return c if c else "USD"


def normalize_impact(impact_str: Any) -> str:
    """Standardize impact to High, Medium, Low, or Non-Economic."""
    if not impact_str:
        return "Low"
    s = str(impact_str).strip().lower()
    if "high" in s:
        return "High"
    if "medium" in s or re.search(r"\bmed\b", s):
        return "Medium"
    if "low" in s:
        return "Low"
    if "holiday" in s or "non" in s:
        return "Non-Economic"
    return "Low"


def normalize_event_name(name: Any) -> str:
    """Clean extra spaces while preserving the source event name."""
    if not name:
        return ""
    return " ".join(str(name).strip().split())


def _get_timezone(name: str) -> timezone | ZoneInfo:
    if name.upper() in {"UTC", "GMT", "Z"}:
        return timezone.utc
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown source timezone: {name}") from exc


def parse_iso_datetime(dt_str: str, default_timezone_name: str = "UTC") -> datetime:
    """Parse an ISO datetime and return a timezone-aware UTC datetime."""
    dt_str = dt_str.strip()
    if dt_str.endswith("Z"):
        dt_str = dt_str[:-1] + "+00:00"
    dt = datetime.fromisoformat(dt_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_get_timezone(default_timezone_name))
    return dt.astimezone(timezone.utc)


def parse_date_time_components(
    date_str: str,
    time_str: Optional[str] = None,
    source_timezone_name: str = "UTC",
) -> datetime:
    """
    Parse separate date/time components using an IANA timezone identifier.
    DST is handled by zoneinfo rather than a fixed UTC offset.
    """
    date_str = date_str.strip()
    time_str = (time_str or "").strip()

    if "-" in date_str:
        parts = date_str.split("-")
        if len(parts[0]) == 4:
            year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        else:
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
    normalized_time = time_str.lower()
    if normalized_time not in ("all day", "tentative", "day 1", "day 2", "day 3", "none", ""):
        match = re.match(r"^(\d{1,2}):(\d{2})\s*([ap]m)?$", normalized_time)
        if match:
            h = int(match.group(1))
            minute = int(match.group(2))
            meridiem = match.group(3)
            if meridiem == "pm" and h < 12:
                h += 12
            elif meridiem == "am" and h == 12:
                h = 0
            hour = h

    source_tz = _get_timezone(source_timezone_name)
    local_dt = datetime(year, month, day, hour, minute, tzinfo=source_tz)
    return local_dt.astimezone(timezone.utc)


def normalize_timestamp(
    raw_date: Any,
    raw_time: Optional[Any] = None,
    source_timezone_name: str = "UTC",
) -> datetime:
    """Return a timezone-aware UTC timestamp without guessing a fixed offset."""
    if isinstance(raw_date, datetime):
        dt = raw_date
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_get_timezone(source_timezone_name))
        return dt.astimezone(timezone.utc)

    if raw_date is None:
        raise ValueError("Missing event date/timestamp")

    s_date = str(raw_date).strip()
    s_time = str(raw_time).strip() if raw_time is not None else ""

    if "T" in s_date or (len(s_date) >= 19 and " " in s_date and "-" in s_date):
        try:
            return parse_iso_datetime(s_date, default_timezone_name=source_timezone_name)
        except ValueError:
            pass

    return parse_date_time_components(
        s_date,
        s_time,
        source_timezone_name=source_timezone_name,
    )


def build_source_event_key(source: str, timestamp_utc: datetime, currency: str, event_name: str) -> str:
    """Build a deterministic source key for idempotent upserts."""
    timestamp_utc = timestamp_utc.astimezone(timezone.utc)
    ts_str = timestamp_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    clean_event = normalize_event_name(event_name)
    clean_curr = normalize_currency(currency)
    return f"{source.lower()}|{ts_str}|{clean_curr}|{clean_event}"


def normalize_event_record(
    raw: Dict[str, Any],
    source: str = "forexfactory",
    source_timezone_name: str = "UTC",
) -> Dict[str, Any]:
    """Normalize a raw event record into the server's canonical shape."""
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
    timestamp_utc = normalize_timestamp(
        raw_date,
        raw_time,
        source_timezone_name=source_timezone_name,
    )

    return {
        "source": source,
        "source_event_key": build_source_event_key(source, timestamp_utc, currency, event_name),
        "event": event_name,
        "event_type": raw.get("event_type"),
        "currency": currency,
        "impact": impact,
        "timestamp_utc": timestamp_utc,
        "actual": normalize_raw_value(raw_actual),
        "forecast": normalize_raw_value(raw_forecast),
        "previous": normalize_raw_value(raw_previous),
        "detail_url": str(raw_url).strip() if raw_url else None,
        "source_url": raw.get("source_url"),
    }
