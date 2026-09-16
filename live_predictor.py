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

def fetch_this_week():
    try:
        xml_data = requests.get(FF_XML_URL).text
        root = ET.fromstring(xml_data)
        events = []
        for node in root.findall('event'):
            impact = node.find('impact').text
            if impact != 'High': continue
            
            currency = node.find('country').text
            if currency != 'USD': continue
            
            title = node.find('title').text
            forecast = clean_val(node.find('forecast').text)
            actual = clean_val(node.find('actual').text)
            
            # Simple date parsing
            date_str = node.find('date').text
            time_str = node.find('time').text
            try:
                # MM-DD-YYYY h:mma
                dt = datetime.strptime(f"{date_str} {time_str}", "%m-%d-%Y %I:%M%p")
                events.append({"title": title, "dt": dt, "forecast": forecast, "actual": actual})
            except Exception:
                pass
        return sorted(events, key=lambda x: x["dt"])
    except Exception as e:
        print(f"[Error] Failed to fetch ForexFactory XML: {e}")
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

def find_precursor(events, title_substring):
    # Try to find it in this week's events (it must have already happened, so actual is not None)
    for e in events:
        if title_substring.lower() in e["title"].lower() and e["actual"] is not None:
            return e
    # If not found, prompt the user
    return prompt_for_precursor(title_substring)

def predict(target_event, all_events):
    title = target_event["title"]
    
    if "Farm" in title:
        print("-> Target: Non-Farm Payrolls (NFP). Gathering precursors...")
        adp = find_precursor(all_events, "ADP Non-Farm")
        ism_srv = find_precursor(all_events, "ISM Services")
        
        score = calc_score(adp["actual"], adp["forecast"]) * 1.5 + calc_score(ism_srv["actual"], ism_srv["forecast"]) * 1.0
        
        bias = "BUY" if score >= 1.0 else ("SELL" if score <= -1.0 else "SKIP")
        return bias, score
        
    if "CPI" in title:
        print("-> Target: Consumer Price Index (CPI). Gathering precursors...")
        ism_mfg = find_precursor(all_events, "ISM Manufacturing PMI")
        
        score = calc_score(ism_mfg["actual"], ism_mfg["forecast"]) * 1.0
        bias = "BUY" if score >= 1.0 else ("SELL" if score <= -1.0 else "SKIP")
        return bias, score
        
    if "Retail" in title:
        print("-> Target: Retail Sales. Gathering precursors...")
        conf = find_precursor(all_events, "CB Consumer Confidence")
        
        score = calc_score(conf["actual"], conf["forecast"]) * 2.0
        bias = "BUY" if score >= 1.0 else ("SELL" if score <= -1.0 else "SKIP")
        return bias, score

    return "SKIP", 0

def main():
    print("=== News Trader AI : Live Autonomous Predictor ===")
    print("Fetching live ForexFactory XML...")
    events = fetch_this_week()
    
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
    
    bias, score = predict(target, events)
    
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
