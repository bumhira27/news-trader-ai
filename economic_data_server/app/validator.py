from datetime import datetime, timezone
from typing import Dict, Any, Tuple, Optional, Set, List

class ValidationError(Exception):
    pass

def validate_event_record(
    record: Dict[str, Any],
    seen_keys: Optional[Set[str]] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> Tuple[bool, Optional[str]]:
    """
    Validate a single normalized event record.
    Returns (is_valid, error_reason).
    """
    # 1. Required fields
    if not record.get("event") or not str(record["event"]).strip():
        return False, "Missing or empty event name"
    if not record.get("currency") or not str(record["currency"]).strip():
        return False, "Missing or empty currency"
    if not record.get("source") or not str(record["source"]).strip():
        return False, "Missing or empty source"
    if not record.get("source_event_key") or not str(record["source_event_key"]).strip():
        return False, "Missing or empty source_event_key"

    # 2. Timestamp validation
    ts = record.get("timestamp_utc")
    if ts is None or not isinstance(ts, datetime):
        return False, "Timestamp is missing or invalid datetime object"

    # 3. Duplicate key in batch validation
    key = record["source_event_key"]
    if seen_keys is not None:
        if key in seen_keys:
            return False, f"Duplicate source_event_key in batch: {key}"
        seen_keys.add(key)

    # 4. Date range boundary validation (if start/end given)
    # Normalize comparison datetimes to UTC
    if start_date is not None:
        s_dt = start_date if start_date.tzinfo is not None else start_date.replace(tzinfo=timezone.utc)
        if ts < s_dt:
            return False, f"Event timestamp {ts} is before requested start {s_dt}"

    if end_date is not None:
        e_dt = end_date if end_date.tzinfo is not None else end_date.replace(tzinfo=timezone.utc)
        if ts > e_dt:
            return False, f"Event timestamp {ts} is after requested end {e_dt}"

    # Note: actual, forecast, previous may legitimately be None/empty (e.g. pre-release events)
    return True, None

def validate_batch(
    records: List[Dict[str, Any]],
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> Tuple[List[Dict[str, Any]], List[Tuple[Dict[str, Any], str]]]:
    """
    Validate a batch of records.
    Returns (valid_records, rejected_records_with_reasons).
    """
    valid = []
    rejected = []
    seen_keys: Set[str] = set()

    for r in records:
        is_valid, err = validate_event_record(r, seen_keys=seen_keys, start_date=start_date, end_date=end_date)
        if is_valid:
            valid.append(r)
        else:
            rejected.append((r, err or "Unknown validation error"))

    return valid, rejected
