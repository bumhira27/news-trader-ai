import sys
import time
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

BIAS_FILE_PATH = r"C:\news_bias.txt"
FF_XML_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"

def clean_val(s):
    if not s: return None
    s = s.replace("%", "").replace("K", "").replace("M", "").replace("B", "").replace(",", "")
    try: return float(s)
    except: return None

def calc_score(actual, forecast, inverse=False):
    if actual is None or forecast is None: return 0
    if actual > forecast: return 1 if inverse else -1
    if actual < forecast: return -1 if inverse else 1
    return 0

def fetch_this_week(context_engine: 'ContextEngine'):
    try:
        now = datetime.now()
        start_str = now.replace(hour=0, minute=0, second=0).isoformat() + "Z"
        # Fetch upcoming events via context engine
        events = context_engine.fetch_events(currency="USD", impact="High", start=start_str, limit=50)
        
        parsed_events = []
        for e in events:
            parsed_events.append({
                "title": e.get("event"),
                "dt": e.get("_dt") or datetime.fromisoformat(e["timestamp_utc"].replace("Z", "+00:00")).replace(tzinfo=None),
                "forecast": clean_val(e.get("forecast")),
                "actual": clean_val(e.get("actual"))
            })
        return sorted(parsed_events, key=lambda x: x["dt"])
    except Exception as e:
        print(f"[Error] Failed to fetch events from Economic Data API: {e}")
        return []

def prompt_for_precursor(title):
    print(f"\n[MANUAL INPUT REQUIRED]")
    print(f"I need the precursor data for: '{title}'.")
    print("Since it is not in this week's XML feed, please check the ForexFactory calendar.")
    
    while True:
        try:
            act_str = input(f"Enter ACTUAL for {title} (e.g. 150): ").strip()
            for_str = input(f"Enter FORECAST for {title} (e.g. 160): ").strip()
            return {"actual": float(act_str), "forecast": float(for_str)}
        except ValueError:
            print("Invalid input. Please enter numbers only.")

from data.context_engine import ContextEngine

def find_precursor(events, title_substring, context_engine=None, target_dt=None):
    # Try to find in current events feed
    for e in events:
        if title_substring.lower() in e["title"].lower() and e.get("actual") is not None:
            return e

    # Query Economic Context Engine API for historical precursor releases
    if context_engine and target_dt:
        release = context_engine.get_latest_release(title_substring, target_dt)
        if release and release.get("actual") is not None and release.get("forecast") is not None:
            act = clean_val(release.get("actual"))
            fcst = clean_val(release.get("forecast"))
            if act is not None and fcst is not None:
                print(f"[Context Engine] Retrieved historical precursor '{release.get('event')}': Actual={release.get('actual')}, Forecast={release.get('forecast')}")
                return {"title": release.get("event"), "actual": act, "forecast": fcst}

    # If not found, prompt the user
    return prompt_for_precursor(title_substring)

def predict(target_event, all_events, context_engine=None):
    title = target_event["title"]
    target_dt = target_event["dt"]
    
    if "Farm" in title:
        print("-> Target: Non-Farm Payrolls (NFP). Gathering precursors...")
        adp = find_precursor(all_events, "ADP Non-Farm", context_engine=context_engine, target_dt=target_dt)
        ism_srv = find_precursor(all_events, "ISM Services", context_engine=context_engine, target_dt=target_dt)
        
        score = calc_score(adp["actual"], adp["forecast"]) * 1.5 + calc_score(ism_srv["actual"], ism_srv["forecast"]) * 1.0
        
        bias = "BUY" if score >= 1.0 else ("SELL" if score <= -1.0 else "SKIP")
        return bias, score
        
    if "CPI" in title:
        print("-> Target: Consumer Price Index (CPI). Gathering precursors...")
        ism_mfg = find_precursor(all_events, "ISM Manufacturing PMI", context_engine=context_engine, target_dt=target_dt)
        
        score = calc_score(ism_mfg["actual"], ism_mfg["forecast"]) * 1.0
        bias = "BUY" if score >= 1.0 else ("SELL" if score <= -1.0 else "SKIP")
        return bias, score
        
    if "Retail" in title:
        print("-> Target: Retail Sales. Gathering precursors...")
        conf = find_precursor(all_events, "CB Consumer Confidence", context_engine=context_engine, target_dt=target_dt)
        
        score = calc_score(conf["actual"], conf["forecast"]) * 2.0
        bias = "BUY" if score >= 1.0 else ("SELL" if score <= -1.0 else "SKIP")
        return bias, score

    return "SKIP", 0

def main():
    print("=== News Trader AI : Live Autonomous Predictor ===")
    
    from data.context_engine import ContextEngine
    engine = ContextEngine()
    
    print("Fetching live events from Economic Data API...")
    events = fetch_this_week(engine)
    
    if not events:
        print("No USD High-Impact events found this week.")
        return
        
    now = datetime.now()
    future_events = [e for e in events if e["dt"] > now]
    
    target = None
    for e in future_events:
        t = e["title"]
        if "Farm" in t or "CPI" in t or "Retail" in t:
            target = e
            break
            
    if not target:
        print("No Holy Trinity events (NFP, CPI, Retail Sales) found in the upcoming schedule.")
        return
        
    print(f"\n[TARGET LOCKED]: {target['title']} @ {target['dt']} (Local Time)")
    
    engine = ContextEngine()
    bias, score = predict(target, events, context_engine=engine)
    
    if bias == "SKIP":
        print("\n[RESULT] AI determined there is NO CLEAR EDGE based on precursor divergence. Skipping trade.")
        if Path(BIAS_FILE_PATH).exists():
            Path(BIAS_FILE_PATH).unlink()
    else:
        print(f"\n[RESULT] Directional Bias Calculated: {bias} (Score: {score})")
        with open(BIAS_FILE_PATH, "w") as f:
            f.write(bias)
        print(f"Bias successfully written to {BIAS_FILE_PATH}")
        print("You may now launch the cTrader EAs. They will automatically detect this file.")

if __name__ == "__main__":
    main()
