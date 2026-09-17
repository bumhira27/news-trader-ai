import os
import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any
import requests

logger = logging.getLogger(__name__)

def parse_numeric_val(s: Optional[str]) -> Optional[float]:
    """Helper to parse numeric value from economic string (e.g. 3.7%, 245K, 1.2M, -0.4%)."""
    if not s:
        return None
    cleaned = s.replace("%", "").replace(",", "").strip()
    multiplier = 1.0
    if cleaned.endswith("K") or cleaned.endswith("k"):
        cleaned = cleaned[:-1]
        multiplier = 1000.0
    elif cleaned.endswith("M") or cleaned.endswith("m"):
        cleaned = cleaned[:-1]
        multiplier = 1000000.0
    elif cleaned.endswith("B") or cleaned.endswith("b"):
        cleaned = cleaned[:-1]
        multiplier = 1000000000.0

    try:
        return float(cleaned) * multiplier
    except ValueError:
        return None

class ContextEngine:
    """
    Lightweight Economic Context Engine for News Trader AI.
    Queries the dedicated Economic Data API for factual macroeconomic events
    and derives analytical context (surprise, deviations, precursor metrics).
    """

    def __init__(
        self,
        api_base_url: Optional[str] = None,
        timeout: int = 5,
        fallback_events: Optional[List[Dict[str, Any]]] = None
    ):
        self.api_base_url = (api_base_url or os.getenv("ECONOMIC_DATA_API_URL", "http://localhost:8000/api/v1")).rstrip("/")
        self.timeout = timeout
        self._fallback_events = fallback_events or []
        self._cache: List[Dict[str, Any]] = []

    def fetch_events(
        self,
        currency: str = "USD",
        impact: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        event: Optional[str] = None,
        limit: int = 200
    ) -> List[Dict[str, Any]]:
        """Query Economic Data API for calendar facts."""
        params = {"currency": currency, "limit": limit}
        if impact:
            params["impact"] = impact
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        if event:
            params["event"] = event

        url = f"{self.api_base_url}/events"
        try:
            res = requests.get(url, params=params, timeout=self.timeout)
            res.raise_for_status()
            events = res.json()
            for e in events:
                if isinstance(e.get("timestamp_utc"), str):
                    e["_dt"] = datetime.fromisoformat(e["timestamp_utc"].replace("Z", "+00:00"))
            return sorted(events, key=lambda x: x["_dt"])
        except Exception as e:
            logger.warning(f"Failed to query Economic Data API at {url} ({e}). Using cached/fallback context.")
            if self._fallback_events:
                res = []
                for ev in self._fallback_events:
                    if currency and ev.get("currency") and ev.get("currency") != currency:
                        continue
                    if impact and ev.get("impact") and ev.get("impact") != impact:
                        continue
                    if event and event.lower() not in ev.get("event", "").lower():
                        continue
                    ev_dt = ev.get("_dt")
                    if not ev_dt and isinstance(ev.get("timestamp_utc"), str):
                        ev_dt = datetime.fromisoformat(ev["timestamp_utc"].replace("Z", "+00:00"))
                        ev["_dt"] = ev_dt
                    if start and ev_dt:
                        st_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                        if ev_dt < st_dt:
                            continue
                    if end and ev_dt:
                        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
                        if ev_dt > end_dt:
                            continue
                    res.append(ev)
                return sorted(res, key=lambda x: x.get("_dt") or datetime.min.replace(tzinfo=timezone.utc))[:limit]
            return []

    def get_latest_release(self, event_keyword: str, before_dt: datetime, currency: str = "USD") -> Optional[Dict[str, Any]]:
        """
        Find the most recent released event matching event_keyword strictly before before_dt.
        """
        before_str = before_dt.isoformat()
        events = self.fetch_events(currency=currency, event=event_keyword, end=before_str, limit=50)

        # Iterate backwards to find release strictly before target datetime
        for e in reversed(events):
            if event_keyword.lower() not in e.get("event", "").lower():
                continue
            e_dt = e.get("_dt")
            if not e_dt and isinstance(e.get("timestamp_utc"), str):
                e_dt = datetime.fromisoformat(e["timestamp_utc"].replace("Z", "+00:00"))
            if e_dt and e_dt < before_dt:
                # Attach derived context in News Trader AI
                act = parse_numeric_val(e.get("actual"))
                fcst = parse_numeric_val(e.get("forecast"))
                if act is not None and fcst is not None:
                    e["surprise"] = act - fcst
                else:
                    e["surprise"] = None
                return e
        return None

    def calculate_surprise(self, actual_str: Optional[str], forecast_str: Optional[str]) -> Optional[float]:
        """Compute raw economic surprise in News Trader AI layer."""
        act = parse_numeric_val(actual_str)
        fcst = parse_numeric_val(forecast_str)
        if act is not None and fcst is not None:
            return act - fcst
        return None

    def calculate_forecast_deviation(self, forecast_str: Optional[str], previous_str: Optional[str]) -> Optional[float]:
        """Compute forecast deviation against previous release in News Trader AI layer."""
        fcst = parse_numeric_val(forecast_str)
        prev = parse_numeric_val(previous_str)
        if fcst is not None and prev is not None:
            return fcst - prev
        return None

    def build_fomc_context(self, target_timestamp_utc: str) -> str:
        """
        Builds the precursor context block required for an FOMC decision.
        """
        target_dt = datetime.fromisoformat(target_timestamp_utc.replace("Z", "+00:00"))

        precursors = {
            "CPI": "CPI",
            "NFP": "Nonfarm Payrolls",
            "PCE": "PCE"
        }

        context_lines = []
        for label, keyword in precursors.items():
            release = self.get_latest_release(keyword, target_dt)
            if release:
                act = release.get("actual") or "N/A"
                fcst = release.get("forecast") or "N/A"
                prev = release.get("previous") or "N/A"
                surp = release.get("surprise")

                surp_str = f"{surp:+.2f}" if surp is not None else "N/A"
                line = f"Previous {label}: Actual = {act} Forecast = {fcst} Previous = {prev} Surprise = {surp_str}"
                context_lines.append(line)
            else:
                context_lines.append(f"Previous {label}: [No historical release found before this event]")

        return "\n".join(context_lines)

if __name__ == "__main__":
    engine = ContextEngine()
    print("News Trader AI Context Engine Ready.")
