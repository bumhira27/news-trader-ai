import argparse
import calendar
import logging
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from .db import SessionLocal, init_db
from .models import EconomicEvent, IngestionRun, EventRevision
from .normalizer import normalize_event_record
from .validator import validate_batch
from .providers.forexfactory import ForexFactoryProvider, ProviderError

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ingest")

def get_month_range(year: int, month: int) -> tuple[datetime, datetime]:
    """Calculate exact UTC start and end bounds for a given year and month."""
    _, last_day = calendar.monthrange(year, month)
    start_dt = datetime(year, month, 1, 0, 0, 0, tzinfo=timezone.utc)
    end_dt = datetime(year, month, last_day, 23, 59, 59, 999999, tzinfo=timezone.utc)
    return start_dt, end_dt

def run_ingestion(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    latest: bool = False,
    file_path: Optional[str] = None,
    db: Optional[Session] = None
) -> Dict[str, Any]:
    """
    Execute the economic data ingestion pipeline with idempotent upsert.
    """
    own_session = False
    if db is None:
        init_db()
        db = SessionLocal()
        own_session = True

    provider = ForexFactoryProvider()
    source_name = provider.source_name

    # Create ingestion run log
    req_start_str = start_date.strftime("%Y-%m-%d") if start_date else None
    req_end_str = end_date.strftime("%Y-%m-%d") if end_date else None

    run_record = IngestionRun(
        started_at=datetime.now(timezone.utc),
        source=source_name,
        requested_start=req_start_str,
        requested_end=req_end_str,
        status="running"
    )
    db.add(run_record)
    db.commit()
    db.refresh(run_record)

    try:
        # 1. Fetch raw records
        logger.info(f"Fetching records (start={req_start_str}, end={req_end_str}, latest={latest}, file={file_path})")

        raw_records: List[Dict[str, Any]] = []
        if file_path:
            raw_records = provider.load_from_file(file_path)
        elif latest:
            raw_records = provider.fetch_latest()
        elif start_date and end_date:
            # Check for local monthly fixture if past month
            fixture_candidate = Path(__file__).resolve().parent.parent / "fixtures" / f"forexfactory_{start_date.year}_{start_date.month:02d}.json"
            if fixture_candidate.exists():
                logger.info(f"Using monthly historical fixture: {fixture_candidate}")
                raw_records = provider.load_from_file(fixture_candidate)
            else:
                raw_records = provider.fetch_events(start_date=start_date, end_date=end_date)
        else:
            raw_records = provider.fetch_latest()

        run_record.records_found = len(raw_records)
        logger.info(f"Retrieved {len(raw_records)} raw records from {source_name}")

        # 2. Normalize records
        normalized_records = []
        for raw in raw_records:
            try:
                norm = normalize_event_record(raw, source=source_name)
                normalized_records.append(norm)
            except Exception as e:
                logger.warning(f"Normalization failed for record: {e}")
                run_record.records_rejected += 1

        # 3. Validate records against schema and date boundaries
        valid_records, rejected_records = validate_batch(
            normalized_records,
            start_date=start_date,
            end_date=end_date
        )

        run_record.records_rejected += len(rejected_records)
        for r, reason in rejected_records:
            logger.warning(f"Validation rejected record {r.get('event')} @ {r.get('timestamp_utc')}: {reason}")

        # 4. Idempotent Upsert into database
        inserted_count = 0
        updated_count = 0

        for item in valid_records:
            source_key = item["source_event_key"]
            existing = db.query(EconomicEvent).filter(EconomicEvent.source_event_key == source_key).first()

            if existing:
                # Check for changes in actual, forecast, or previous
                changed = False
                for field in ("actual", "forecast", "previous", "impact", "detail_url"):
                    new_val = item.get(field)
                    old_val = getattr(existing, field)
                    if new_val != old_val:
                        changed = True
                        # Track revision for economic values
                        if field in ("actual", "forecast", "previous"):
                            rev = EventRevision(
                                event_id=existing.id,
                                field_name=field,
                                old_value=old_val,
                                new_value=new_val,
                                changed_at=datetime.now(timezone.utc)
                            )
                            db.add(rev)
                        setattr(existing, field, new_val)

                if changed:
                    existing.updated_at = datetime.now(timezone.utc)
                    updated_count += 1
            else:
                new_event = EconomicEvent(
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
                    source_url=item.get("source_url")
                )
                db.add(new_event)
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
            "records_rejected": run_record.records_rejected
        }

        logger.info(
            f"Ingestion complete: Found={run_record.records_found}, "
            f"Inserted={inserted_count}, Updated={updated_count}, "
            f"Rejected={run_record.records_rejected}"
        )
        return result

    except Exception as e:
        db.rollback()
        run_record.status = "failed"
        run_record.error_message = str(e)
        run_record.finished_at = datetime.now(timezone.utc)
        db.commit()
        logger.error(f"Ingestion failed: {e}", exc_info=True)
        raise
    finally:
        if own_session:
            db.close()

def main():
    parser = argparse.ArgumentParser(description="Forex Factory Economic Data Ingestion CLI")
    parser.add_argument("--year", type=int, help="Historical year (e.g. 2026)")
    parser.add_argument("--month", type=int, help="Historical month (1-12)")
    parser.add_argument("--start", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, help="End date (YYYY-MM-DD)")
    parser.add_argument("--latest", action="store_true", help="Ingest current week release data")
    parser.add_argument("--file", type=str, help="Path to local fixture or export file")

    args = parser.parse_args()

    start_date = None
    end_date = None

    if args.year and args.month:
        start_date, end_date = get_month_range(args.year, args.month)
    elif args.start and args.end:
        start_date = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end_date = datetime.strptime(args.end, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
    elif not args.latest and not args.file:
        print("Error: Must specify either (--year and --month), (--start and --end), --latest, or --file")
        sys.exit(1)

    try:
        res = run_ingestion(
            start_date=start_date,
            end_date=end_date,
            latest=args.latest,
            file_path=args.file
        )
        print("\n=== Ingestion Result ===")
        for k, v in res.items():
            print(f"  {k}: {v}")
    except Exception as e:
        print(f"\nIngestion failed with error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
