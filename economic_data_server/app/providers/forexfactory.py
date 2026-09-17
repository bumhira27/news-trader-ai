import calendar
import csv
import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, date, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests
from bs4 import BeautifulSoup

from .base import BaseCalendarProvider

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    pass


class ForexFactoryProvider(BaseCalendarProvider):
    """
    Forex Factory economic-calendar provider.

    Live data uses the lightweight FairEconomy weekly JSON/XML export.
    Historical data uses Forex Factory's month calendar pages because the
    weekly export is intentionally limited to the current week.
    """

    FF_JSON_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    FF_XML_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
    FF_MONTH_URL = "https://www.forexfactory.com/calendar?month={month}.{year}"

    def __init__(self, request_timeout: int = 20, max_retries: int = 3):
        self.request_timeout = request_timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/140 Safari/537.36 "
                    "NewsTraderAI-EconomicDataServer/1.1"
                )
            }
        )

    @property
    def source_name(self) -> str:
        return "forexfactory"

    def _get_with_retry(self, url: str) -> requests.Response:
        delay = 2.0
        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(url, timeout=self.request_timeout)
                if response.status_code == 429:
                    logger.warning(
                        "Rate limited by %s. Waiting %.1fs (attempt %s/%s)",
                        url,
                        delay,
                        attempt,
                        self.max_retries,
                    )
                    time.sleep(delay)
                    delay *= 2
                    continue

                response.raise_for_status()
                return response
            except requests.RequestException as exc:
                last_error = exc
                if attempt == self.max_retries:
                    break
                time.sleep(delay)
                delay *= 2

        raise ProviderError(f"Failed to fetch Forex Factory data from {url}: {last_error}")

    def fetch_latest(self, format_preference: str = "json", **kwargs) -> List[Dict[str, Any]]:
        """Fetch the current week's calendar from the FairEconomy export."""
        file_path = kwargs.get("file_path")
        if file_path:
            return self.load_from_file(file_path)

        if format_preference == "json":
            try:
                response = self._get_with_retry(self.FF_JSON_URL)
                payload = response.json()
                if isinstance(payload, list):
                    return payload
            except Exception as exc:
                logger.warning("Forex Factory JSON export failed: %s; trying XML", exc)

        try:
            response = self._get_with_retry(self.FF_XML_URL)
            return self._parse_xml(response.text)
        except Exception as exc:
            raise ProviderError(f"All current Forex Factory exports failed: {exc}") from exc

    def fetch_events(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """
        Fetch events for a date range.

        A historical range is retrieved from the corresponding Forex Factory
        monthly calendar page(s). A current/no-range request uses the weekly
        FairEconomy export.
        """
        file_path = kwargs.get("file_path")
        if file_path:
            return self.load_from_file(file_path)

        if start_date and end_date:
            return self._fetch_historical_range(start_date, end_date)

        return self.fetch_latest(**kwargs)

    def _fetch_historical_range(self, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        if end_date < start_date:
            raise ValueError("end_date must be greater than or equal to start_date")

        start_month = date(start_date.year, start_date.month, 1)
        end_month = date(end_date.year, end_date.month, 1)
        cursor = start_month
        all_events: List[Dict[str, Any]] = []

        while cursor <= end_month:
            month_name = cursor.strftime("%b").lower()
            url = self.FF_MONTH_URL.format(month=month_name, year=cursor.year)
            logger.info("Fetching historical Forex Factory month: %s", url)
            response = self._get_with_retry(url)
            month_events = self._parse_html(response.text, source_url=url, year=cursor.year)
            all_events.extend(month_events)

            if cursor.month == 12:
                cursor = date(cursor.year + 1, 1, 1)
            else:
                cursor = date(cursor.year, cursor.month + 1, 1)

        return all_events

    def load_from_file(self, path: str | Path) -> List[Dict[str, Any]]:
        """Load explicit local test/import files (JSON, XML, or CSV)."""
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Calendar file not found: {file_path}")

        ext = file_path.suffix.lower()
        if ext == ".json":
            with file_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, list) else data.get("events", [])

        if ext == ".xml":
            return self._parse_xml(file_path.read_text(encoding="utf-8"))

        if ext == ".csv":
            with file_path.open("r", encoding="utf-8", newline="") as handle:
                return [dict(row) for row in csv.DictReader(handle)]

        raise ValueError(f"Unsupported calendar file format: {ext}")

    def _parse_xml(self, xml_text: str) -> List[Dict[str, Any]]:
        """Parse FairEconomy weekly XML."""
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            raise ProviderError(f"Error parsing Forex Factory XML: {exc}") from exc

        events: List[Dict[str, Any]] = []
        for node in root.findall("event"):
            def text(tag: str) -> Optional[str]:
                child = node.find(tag)
                return child.text if child is not None else None

            events.append(
                {
                    "title": text("title"),
                    "country": text("country"),
                    "date": text("date"),
                    "time": text("time"),
                    "impact": text("impact"),
                    "forecast": text("forecast"),
                    "previous": text("previous"),
                    "actual": text("actual"),
                    "url": text("url"),
                }
            )
        return events

    @staticmethod
    def _extract_page_timezone(page_text: str) -> timezone | ZoneInfo:
        match = re.search(r"Calendar\s+Time\s+Zone:\s*([A-Za-z0-9_+\-./]+)", page_text)
        if not match:
            logger.warning("Forex Factory page timezone was not exposed; assuming UTC")
            return timezone.utc

        zone_name = match.group(1)
        if zone_name.upper() in {"UTC", "GMT"}:
            return timezone.utc

        try:
            return ZoneInfo(zone_name)
        except ZoneInfoNotFoundError:
            logger.warning("Unknown Forex Factory page timezone %r; assuming UTC", zone_name)
            return timezone.utc

    @staticmethod
    def _parse_display_date(text: str, year: int) -> Optional[date]:
        match = re.search(r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Z][a-z]{2})\s+(\d{1,2})\b", text)
        if not match:
            return None
        try:
            return datetime.strptime(
                f"{match.group(1)} {match.group(2)} {year}",
                "%b %d %Y",
            ).date()
        except ValueError:
            return None

    @staticmethod
    def _parse_time(text: str) -> tuple[int, int]:
        cleaned = " ".join(text.split()).strip()
        if not cleaned or cleaned.lower() in {"all day", "tentative"} or cleaned.lower().startswith("day "):
            return 0, 0

        match = re.search(r"(\d{1,2}):(\d{2})\s*([ap]m)", cleaned.lower())
        if not match:
            return 0, 0

        hour = int(match.group(1))
        minute = int(match.group(2))
        if match.group(3) == "pm" and hour < 12:
            hour += 12
        if match.group(3) == "am" and hour == 12:
            hour = 0
        return hour, minute

    @staticmethod
    def _parse_impact(cell) -> str:
        classes = " ".join(cell.get("class", [])) if cell else ""
        title = " ".join(
            element.get("title", "")
            for element in cell.find_all(True)
        ).lower() if cell else ""

        text = cell.get_text(" ", strip=True).lower() if cell else ""
        combined = f"{classes.lower()} {title} {text}"

        if "calendar__impact--high" in combined or "impact-red" in combined or "high impact" in combined:
            return "High"
        if "calendar__impact--medium" in combined or "impact-yel" in combined or "medium impact" in combined:
            return "Medium"
        if "calendar__impact--low" in combined or "impact-green" in combined or "low impact" in combined:
            return "Low"
        if "holiday" in combined or "non-economic" in combined:
            return "Non-Economic"
        return "Low"

    @staticmethod
    def _cell_text(row, selector: str) -> str:
        cell = row.select_one(selector)
        return cell.get_text(" ", strip=True) if cell else ""

    def _parse_html(self, html_text: str, source_url: str, year: int) -> List[Dict[str, Any]]:
        """Parse the public Forex Factory historical calendar HTML."""
        soup = BeautifulSoup(html_text, "html.parser")
        rows = soup.select("tr.calendar__row")
        if not rows:
            # Some historical pages use the same row with only calendar_row.
            rows = soup.select("tr.calendar_row")
        if not rows:
            raise ProviderError("Forex Factory historical page contained no calendar rows")

        page_timezone = self._extract_page_timezone(soup.get_text(" ", strip=True))
        current_date: Optional[date] = None
        current_time = (0, 0)
        events: List[Dict[str, Any]] = []

        for row in rows:
            date_cell = row.select_one(".calendar__date")
            if date_cell:
                parsed_date = self._parse_display_date(date_cell.get_text(" ", strip=True), year)
                if parsed_date is not None:
                    current_date = parsed_date
                    current_time = (0, 0)

            if current_date is None:
                continue

            time_text = self._cell_text(row, ".calendar__time")
            if time_text:
                current_time = self._parse_time(time_text)

            currency = self._cell_text(row, ".calendar__currency")
            event_cell = row.select_one(".calendar__event")
            title_node = event_cell.select_one(".calendar__event-title") if event_cell else None
            event_title = (
                title_node.get_text(" ", strip=True)
                if title_node
                else event_cell.get_text(" ", strip=True) if event_cell else ""
            )

            if not currency or not event_title:
                continue

            hour, minute = current_time
            local_dt = datetime(
                current_date.year,
                current_date.month,
                current_date.day,
                hour,
                minute,
                tzinfo=page_timezone,
            )

            event_link = event_cell.select_one("a[href]") if event_cell else None
            detail_url = event_link.get("href") if event_link else None
            if detail_url and detail_url.startswith("/"):
                detail_url = f"https://www.forexfactory.com{detail_url}"

            events.append(
                {
                    "title": event_title,
                    "country": currency,
                    "date": local_dt.isoformat(),
                    "impact": self._parse_impact(row.select_one(".calendar__impact")),
                    "actual": self._cell_text(row, ".calendar__actual") or None,
                    "forecast": self._cell_text(row, ".calendar__forecast") or None,
                    "previous": self._cell_text(row, ".calendar__previous") or None,
                    "url": detail_url,
                    "source_url": source_url,
                }
            )

        return events
