import requests
import xml.etree.ElementTree as ET
import json
from datetime import datetime
from pathlib import Path
import os
import uuid

DB_PATH = Path("calendar_database.json")
FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"

def clean_val(s):
    if not s: return None
    s = s.replace("%", "").replace("K", "").replace("M", "").replace("B", "").replace(",", "")
    try: return float(s)
    except: return None

def update_database():
    print(f"Fetching {FF_URL} ...")
    try:
        xml_data = requests.get(FF_URL).text
        root = ET.fromstring(xml_data)
    except Exception as e:
        print(f"Failed to fetch or parse ForexFactory XML: {e}")
        return

    # Load existing
    if DB_PATH.exists():
        with open(DB_PATH, "r", encoding="utf-8") as f:
            db = json.load(f)
    else:
        db = []

    existing_ids = {e["id"] for e in db}
    new_events = 0

    for node in root.findall('event'):
        currency = node.find('country').text
        if currency != 'USD': continue
        
        impact = node.find('impact').text
        if impact != 'High': continue
        
        title = node.find('title').text
        date_str = node.find('date').text
        time_str = node.find('time').text
        
        fcst_node = node.find('forecast')
        act_node = node.find('actual')
        prev_node = node.find('previous')
        
        forecast = clean_val(fcst_node.text) if fcst_node is not None else None
        actual = clean_val(act_node.text) if act_node is not None else None
        previous = clean_val(prev_node.text) if prev_node is not None else None
        
        try:
            # Parse MM-DD-YYYY h:mma
            dt = datetime.strptime(f"{date_str} {time_str}", "%m-%d-%Y %I:%M%p")
            # Create deterministic ID based on date and title to avoid duplicates
            event_id = f"{dt.strftime('%Y%m%d_%H%M')}_{title.replace(' ', '_').lower()}"
            
            if event_id in existing_ids:
                # Update existing if actual/forecast came in
                for e in db:
                    if e["id"] == event_id:
                        e["actual"] = actual
                        e["forecast"] = forecast
                        e["previous"] = previous
                        if actual is not None and forecast is not None:
                            e["surprise"] = actual - forecast
                continue
                
            surprise = (actual - forecast) if actual is not None and forecast is not None else None
            
            record = {
                "id": event_id,
                "timestamp_utc": dt.isoformat() + "Z", # Approximating UTC for storage consistency
                "currency": currency,
                "event": title,
                "impact": impact,
                "actual": actual,
                "forecast": forecast,
                "previous": previous,
                "surprise": surprise
            }
            db.append(record)
            existing_ids.add(event_id)
            new_events += 1
            
        except Exception as e:
            print(f"Error parsing event {title}: {e}")

    # Save
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2)
        
    print(f"Database updated successfully. Added {new_events} new USD High impact events.")
    print(f"Total events in database: {len(db)}")

if __name__ == "__main__":
    update_database()
