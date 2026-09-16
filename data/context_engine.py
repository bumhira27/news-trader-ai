import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

class ContextEngine:
    def __init__(self, db_path: str = "calendar_database.json"):
        self.db_path = Path(db_path)
        self.events = self._load_db()
        
    def _load_db(self) -> List[Dict]:
        if not self.db_path.exists():
            return []
        with open(self.db_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Ensure timestamps are parsed for easy comparison
            for e in data:
                if isinstance(e["timestamp_utc"], str):
                    e["_dt"] = datetime.fromisoformat(e["timestamp_utc"].replace("Z", "+00:00"))
            return sorted(data, key=lambda x: x["_dt"])
            
    def get_latest_release(self, event_keyword: str, before_dt: datetime) -> Optional[Dict]:
        """
        Finds the most recent completed release of a specific event type strictly BEFORE the target timestamp.
        """
        # Search backwards from the most recent
        for e in reversed(self.events):
            if e["_dt"] < before_dt and event_keyword.lower() in e["event"].lower():
                return e
        return None

    def build_fomc_context(self, target_timestamp_utc: str) -> str:
        """
        Builds the specific precursor context block required for an FOMC decision.
        """
        target_dt = datetime.fromisoformat(target_timestamp_utc.replace("Z", "+00:00"))
        
        precursors = {
            "CPI": "CPI",
            "NFP": "Non Farm Payrolls",
            "PCE": "PCE"
        }
        
        context_lines = []
        for label, keyword in precursors.items():
            release = self.get_latest_release(keyword, target_dt)
            if release:
                act = release.get('actual')
                fcst = release.get('forecast')
                prev = release.get('previous')
                surp = release.get('surprise')
                
                # Format gracefully if None
                act_str = f"{act}" if act is not None else "N/A"
                fcst_str = f"{fcst}" if fcst is not None else "N/A"
                prev_str = f"{prev}" if prev is not None else "N/A"
                surp_str = f"{surp:+.2f}" if surp is not None else "N/A"
                
                line = f"Previous {label}: Actual = {act_str} Forecast = {fcst_str} Previous = {prev_str} Surprise = {surp_str}"
                context_lines.append(line)
            else:
                context_lines.append(f"Previous {label}: [No historical release found before this event]")
                
        return "\n".join(context_lines)

if __name__ == "__main__":
    # Test stub
    engine = ContextEngine()
    print("Context Engine Ready.")
