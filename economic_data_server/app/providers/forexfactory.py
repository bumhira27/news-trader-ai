import csv
import json
import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
import requests

from .base import BaseCalendarProvider

logger = logging.getLogger(__name__)

class ProviderError(Exception):
    pass

class ForexFactoryProvider(BaseCalendarProvider):
    """
    Forex Factory economic calendar provider.
    Supports weekly export feeds (JSON, XML, CSV) and historical file imports.
    """

    FF_JSON_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    FF_XML_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
    FF_CSV_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.csv"

    def __init__(self, request_timeout: int = 15, max_retries: int = 3):
        self.request_timeout = request_timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NewsTraderAI-ContextEngine/1.0"
        })

    @property
    def source_name(self) -> str:
        return "forexfactory"

    def _get_with_retry(self, url: str) -> requests.Response:
        delay = 2.0
        for attempt in range(1, self.max_retries + 1):
            try:
                res = self.session.get(url, timeout=self.request_timeout)
                if res.status_code == 429:
                    logger.warning(f"Rate limited (429) by {url}. Waiting {delay}s (attempt {attempt}/{self.max_retries})")
                    time.sleep(delay)
                    delay *= 2
                    continue
                res.raise_for_status()
                return res
            except requests.RequestException as e:
                if attempt == self.max_retries:
                    raise ProviderError(f"Failed to fetch Forex Factory data from {url}: {e}")
                time.sleep(delay)
                delay *= 2
        raise ProviderError(f"Exceeded max retries fetching {url}")

    def fetch_latest(self, format_preference: str = "json", **kwargs) -> List[Dict[str, Any]]:
        """Fetch the current week's economic events from Forex Factory export."""
        file_path = kwargs.get("file_path")
        if file_path:
            return self.load_from_file(file_path)

        if format_preference == "json":
            try:
                res = self._get_with_retry(self.FF_JSON_URL)
                data = res.json()
                if isinstance(data, list):
                    return data
            except Exception as e:
                logger.warning(f"JSON export failed ({e}), falling back to XML")

        # Fallback to XML
        try:
            res = self._get_with_retry(self.FF_XML_URL)
            return self._parse_xml(res.text)
        except Exception as e:
            raise ProviderError(f"All Forex Factory export formats failed: {e}")

    def fetch_events(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Fetch events for a specified date range.
        If file_path is provided, loads from file.
        Otherwise fetches latest feed and filters by date window.
        """
        file_path = kwargs.get("file_path")
        if file_path:
            records = self.load_from_file(file_path)
        else:
            records = self.fetch_latest(**kwargs)

        return records

    def load_from_file(self, path: str | Path) -> List[Dict[str, Any]]:
        """Load and parse records from local file (JSON, XML, or CSV)."""
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Fixture or calendar file not found: {file_path}")

        ext = file_path.suffix.lower()
        if ext == ".json":
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else data.get("events", [])

        elif ext == ".xml":
            with open(file_path, "r", encoding="utf-8") as f:
                return self._parse_xml(f.read())

        elif ext == ".csv":
            records = []
            with open(file_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    records.append(dict(row))
            return records

        else:
            raise ValueError(f"Unsupported calendar file format: {ext}")

    def _parse_xml(self, xml_text: str) -> List[Dict[str, Any]]:
        """Parse Forex Factory weekly XML format."""
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            raise ProviderError(f"Error parsing Forex Factory XML: {e}")

        events = []
        for node in root.findall("event"):
            title_node = node.find("title")
            country_node = node.find("country")
            date_node = node.find("date")
            time_node = node.find("time")
            impact_node = node.find("impact")
            forecast_node = node.find("forecast")
            previous_node = node.find("previous")
            actual_node = node.find("actual")
            url_node = node.find("url")

            events.append({
                "title": title_node.text if title_node is not None else None,
                "country": country_node.text if country_node is not None else None,
                "date": date_node.text if date_node is not None else None,
                "time": time_node.text if time_node is not None else None,
                "impact": impact_node.text if impact_node is not None else None,
                "forecast": forecast_node.text if forecast_node is not None else None,
                "previous": previous_node.text if previous_node is not None else None,
                "actual": actual_node.text if actual_node is not None else None,
                "url": url_node.text if url_node is not None else None,
            })
        return events
