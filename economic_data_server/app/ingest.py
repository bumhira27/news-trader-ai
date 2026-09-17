import argparse
import calendar
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List

from sqlalchemy.orm import Session

from .db import SessionLocal, init_db
from .models import EconomicEvent, IngestionRun, EventRevision
from .normalizer import normalize_event_record
from .validator import validate_batch
from .providers.forexfactory import ForexFactoryProvider

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ingest")


def get_month_range(year: int, month: int) -> tuple[datetime, datetime]:
    """Return the inclusive UTC bounds for a calendar month."""
    _, last_day = calendar.monthrange(year, month)
    return (
        datetime(year, month, 1, 0, 0, 0, tzinfo=timezone.utc),
        datetime(year, month, last_day, 23, 59, 59, 999999, tzinfo=timezone.utc),
    )


def run_ingestion(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    latest: bool = False,
    file_path: Optional[str] = None,
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    """Fetch, normalize, validate and idempotently upsert economic events."""
    own_session = False
    if db is None:
        init_db()
        db = SessionLocal()
        own_session = True

    provider = ForexFactoryProvider()
    source_name = provider.source_name
    req_start_str = start_date.strftime("%Y-%m-%d") if start_date else None
    req_end_str = end_date.strftime("%Y-%m-%d") if end_date else None

    run_record = IngestionRun(
        started_at=datetime.now(timezone.utc),
        source=source_name,
        requested_start=req_start_str,
        requested_end=req_end_str,
        status="running",
    )
    db.add(run_record)
    db.commit()
    db.refresh(run_record)

    try:
        logger.info(
            "Fetching records (start=%s, end=%s, latest=%s, explicit_file=%s)",
            req_start_str,
            req_end_str,
            latest,
            bool(file_path),
        )

        if file_path:
            # Explicit local files are supported for deterministic tests/imports.
            raw_records = provider.load_from_file(file_path)
        elif latest:
            raw_records = provider.fetch_latest()
        elif start_date and end_date:
            # Historical requests now go to the actual Forex Factory monthly
            # calendar. No fixture is automatically substituted for real data.
            raw_records = provider.fetch_events(start_date=start_date, end_date=end_date)
        else:
            raw_records = provider.fetch_latest()

        run_record.records_found = len(raw_records)
        logger.info("Retrieved %s raw records from %s", len(raw_records), source_name)

        normalized_records: List[Dict[str, Any]] = []
        for raw in raw_records:
            try:
                normalized_records.append(normalize_event_record(raw, source=source_name))
            except Exception as exc:
                logger.warning("Normalization failed for record: %s", exc)
                run_record.records_rejected += 1

        valid_records, rejected_records = validate_batch(
            normalized_records,
            start_date=start_date,
            end_date=end_date,
        )

        run_record.records_rejected += len(rejected_records)
        for record, reason in rejected_records:
            logger.warning(
                "Validation rejected %s @ %s: %s",
                record.get("event"),
                record.get("timestamp_utc"),
                reason,
            )

        inserted_count = 0
        updated_count = 0

        for item in valid_records:
            source_key = item["source_event_key"]
            existing = (
                db.query(EconomicEvent)
                .filter(EconomicEvent.source_event_key == source_key)
                .first()
            )

            if existing:
                changed = False
                for field in ("event_type", "currency", "impact", "actual", "forecast", "previous", "detail_url", "source_url"):
                    new_val = item.get(field)
                    old_val = getattr(existing, field)
                    if new_val == old_val:
                        continue

                    changed = True
                    if field in ("actual", "forecast", "previous"):
                        db.add(
                            EventRevision(
                                event_id=existing.id,
                                field_name=field,
                                old_value=old_val,
                                new_value=new_val,
                                changed_at=datetime.now(timezone.utc),
                            )
                        )
                    setattr(existing, field, new_val)

                if changed:
                    existing.updated_at = datetime.now(timezone.utc)
                    updated_count += 1
                continue

            db.add(
                EconomicEvent(
                    source=item["source"],
                    source_event_key=item["source_event_key"],
                    event=item["event"],
                    event_type=item.get("event_type"),
                    currency=item["currency"],
                    impact=item["impact"],
                    timestamp_utc=item["timestamp_utc"],
                    actual=item.get("actual"),
                    forecast=item.get("forecast"),
                    previous=item.get("previous"),
                    detail_url=item.get("detail_url"),
                    source_url=item.get("source_url"),
                )
            )
            inserted_count += 1

        db.commit()

        run_record.records_inserted = inserted_count
        run_record.records_updated = updated_count
        run_record.status = "success"
        run_record.finished_at = datetime.now(timezone.utc)
        db.commit()

        result = {
            "run_id": run_record.id,
            "status": "success",
            "source": source_name,
            "requested_start": req_start_str,
            "requested_end": req_end_str,
            "records_found": run_record.records_found,
            "records_inserted": inserted_count,
            "records_updated": updated_count,
            "records_rejected": run_record.records_rejected,
        }

        logger.info(
            "Ingestion complete: Found=%s, Inserted=%s, Updated=%s, Rejected=%s",
            run_record.records_found,
            inserted_count,
            updated_count,
            run_record.records_rejected,
        )
        return result

    except Exception as exc:
        db.rollback()
        run_record.status = "failed"
        run_record.error_message = str(exc)
        run_record.finished_at = datetime.now(timezone.utc)
        db.commit()
        logger.error("Ingestion failed: %s", exc, exc_info=True)
        raise
    finally:
        if own_session:
            db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Forex Factory Economic Data Ingestion CLI")
    parser.add_argument("--year", type=int, help="Historical year, e.g. 2026")
    parser.add_argument("--month", type=int, help="Historical month, 1-12")
    parser.add_argument("--start", type=str, help="Start date, YYYY-MM-DD")
    parser.add_argument("--end", type=str, help="End date, YYYY-MM-DD")
    parser.add_argument("--latest", action="store_true", help="Ingest the current weekly release feed")
    parser.add_argument("--file", type=str, help="Explicit local fixture/import file")
    args = parser.parse_args()

    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    if args.year is not None or args.month is not None:
        if args.year is None or args.month is None:
            parser.error("--year and --month must be supplied together")
        start_date, end_date = get_month_range(args.year, args.month)
    elif args.start and args.end:
        start_date = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end_date = datetime.strptime(args.end, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, microsecond=999999, tzinfo=timezone.utc
        )
    elif not args.latest and not args.file:
        parser.error("Use --year/--month, --start/--end, --latest, or --file")

    try:
        result = run_ingestion(
            start_date=start_date,
            end_date=end_date,
            latest=args.latest,
            file_path=args.file,
        )
        print("\n=== Ingestion Result ===")
        for key, value in result.items():
            print(f"  {key}: {value}")
    except Exception as exc:
        print(f"\nIngestion failed with error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
