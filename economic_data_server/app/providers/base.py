from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Any, Optional

class BaseCalendarProvider(ABC):
    """Abstract base class for upstream economic calendar data providers."""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Name of the data source."""
        pass

    @abstractmethod
    def fetch_events(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Fetch raw event records for an optional date window."""
        pass

    @abstractmethod
    def fetch_latest(self, **kwargs) -> List[Dict[str, Any]]:
        """Fetch the most recent/current release events."""
        pass
