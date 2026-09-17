from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

import requests
from dateutil import parser as date_parser
from zoneinfo import ZoneInfo

from .db import upsert_events

FF_BASE = "https://www.forexfactory.com"
FF_TZ = "Europe/London"


class CalendarParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict[str, str]] = []
        self.row: dict[str, str] | None = None
        self.cell: str | None = None
        self.link: str = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        classes = a.get("class", "") or ""
        if tag == "tr" and "calendar__row" in classes:
            self.row = {"date": "", "time": "", "currency": "", "impact": "", "event": "", "actual": "", "forecast": "", "previous": "", "detail_url": "", "dateline": a.get("data-day-dateline", "") or ""}
        if self.row is None:
            return
        if tag == "td":
            self.cell = next((name for name in ("time", "currency", "impact", "event", "actual", "forecast", "previous", "date") if f"calendar__{name}" in classes), None)
        if tag == "span" and self.cell == "impact":
            title = a.get("title")
            if title:
                self.row["impact"] = unescape(title).strip()
            elif "icon--ff-impact-red" in classes:
                self.row["impact"] = "High"
            elif "icon--ff-impact-ora" in classes:
                self.row["impact"] = "Medium"
            elif "icon--ff-impact-yel" in classes:
                self.row["impact"] = "Low"
            elif "icon--ff-impact-gra" in classes:
                self.row["impact"] = "Non-Economic"
        if tag == "a":
            href = a.get("href") or ""
            if href and self.cell in {"event", "impact"}:
                self.row["detail_url"] = href

    def handle_data(self, data: str) -> None:
        if self.row is None or self.cell is None:
            return
        value = " ".join(unescape(data).split())
        if not value:
            return
        current = self.row[self.cell]
        self.row[self.cell] = f"{current} {value}".strip()

    def handle_endtag(self, tag: str) -> None:
        if tag == "td":
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None
            self.cell = None


def week_key(d: date) -> str:
    monday = d.fromordinal(d.toordinal() - d.weekday())
    return monday.strftime("%b%d.%Y").lower()


def parse_ff_time(text: str, event_date: date) -> datetime | None:
    text = " ".join(text.split())
    if not text:
        return None
    if text.lower() in {"all day", "day 1", "tentative"}:
        return datetime.combine(event_date, datetime.min.time(), tzinfo=ZoneInfo(FF_TZ))
    try:
        dt = date_parser.parse(f"{event_date.isoformat()} {text}")
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo(FF_TZ))
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


def make_source_key(event: dict[str, Any]) -> str:
    parts = [
        event["currency"],
        event["event"],
        event["timestamp_utc"].isoformat(),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def fetch_week(week: date, timeout: int = 30) -> list[dict[str, Any]]:
    url = f"{FF_BASE}/calendar?week={week_key(week)}"
    response = requests.get(url, timeout=timeout, headers={"User-Agent": "NewsTraderEconomicDataServer/1.0"})
    response.raise_for_status()

    parser = CalendarParser()
    parser.feed(response.text)

    current_day = week
    previous_time = ""
    events: list[dict[str, Any]] = []
    for row in parser.rows:
        if row["dateline"]:
            try:
                current_day = datetime.fromtimestamp(int(row["dateline"]), tz=ZoneInfo(FF_TZ)).date()
                previous_time = ""
            except (ValueError, OSError, OverflowError):
                pass

        if row["date"]:
            match = row["date"]
            try:
                current_day = date_parser.parse(match).date()
                previous_time = ""
            except (ValueError, TypeError):
                pass

        if not row["currency"] or not row["event"]:
            continue
        time_text = row["time"] or previous_time
        if row["time"]:
            previous_time = row["time"]
        timestamp = parse_ff_time(time_text, current_day)
        if timestamp is None:
            continue

        item: dict[str, Any] = {
            "source": "forexfactory",
            "source_event_key": "",
            "event": row["event"],
            "event_type": None,
            "currency": row["currency"].upper(),
            "impact": row["impact"] or None,
            "timestamp_utc": timestamp,
            "actual": row["actual"] or None,
            "forecast": row["forecast"] or None,
            "previous": row["previous"] or None,
            "detail_url": urljoin(FF_BASE, row["detail_url"]) if row["detail_url"] else None,
            "source_url": url,
        }
        item["source_event_key"] = make_source_key(item)
        events.append(item)
    return events


def import_month(year: int, month: int, timeout: int = 30) -> int:
    first = date(year, month, 1)
    last = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    monday = first.fromordinal(first.toordinal() - first.weekday())
    total = 0
    current = monday
    while current < last:
        events = fetch_week(current, timeout=timeout)
        filtered = [e for e in events if first <= e["timestamp_utc"].astimezone(ZoneInfo(FF_TZ)).date() < last]
        total += upsert_events(filtered)
        current = current.fromordinal(current.toordinal() + 7)
    return total


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Import a historical Forex Factory calendar month")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    args = parser.parse_args()
    print(f"Imported {import_month(args.year, args.month)} events")
