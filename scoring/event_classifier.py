"""
Module to classify economic events and determine trading bias (bullish/bearish/neutral).
"""
import math

def logic_inflation(actual: float, forecast: float, previous: float) -> str:
    """Logic for inflation events (CPI, PCE)."""
    if actual > forecast:
        return 'bearish_gold'
    elif actual < forecast:
        return 'bullish_gold'
    return 'neutral'

def logic_labor_normal(actual: float, forecast: float, previous: float) -> str:
    """Logic for normal labor events (NFP, ADP, Unemployment)."""
    if actual > forecast:
        return 'bearish_gold'
    elif actual < forecast:
        return 'bullish_gold'
    return 'neutral'

def logic_labor_inverse(actual: float, forecast: float, previous: float) -> str:
    """Logic for inverse labor events (Jobless Claims)."""
    if actual > forecast:
        return 'bullish_gold'
    elif actual < forecast:
        return 'bearish_gold'
    return 'neutral'

def logic_growth(actual: float, forecast: float, previous: float) -> str:
    """Logic for growth events (GDP, ISM, Retail Sales)."""
    if actual > forecast:
        return 'bearish_gold'
    elif actual < forecast:
        return 'bullish_gold'
    return 'neutral'

def logic_fed_policy(actual: float, forecast: float, previous: float) -> str:
    """Logic for Fed policy events (Interest Rate)."""
    if actual > forecast:
        return 'bearish_gold'
    elif actual < forecast:
        return 'bullish_gold'
    return 'neutral'

def logic_housing(actual: float, forecast: float, previous: float) -> str:
    """Logic for housing events (Housing Starts, Building Permits)."""
    if actual > forecast:
        return 'bearish_gold'
    elif actual < forecast:
        return 'bullish_gold'
    return 'neutral'

EVENT_CATEGORIES = {
    'CPI': {'category': 'inflation', 'logic': logic_inflation},
    'PCE': {'category': 'inflation', 'logic': logic_inflation},
    'NFP': {'category': 'labor', 'logic': logic_labor_normal},
    'Non-Farm Employment Change': {'category': 'labor', 'logic': logic_labor_normal},
    'ADP': {'category': 'labor', 'logic': logic_labor_normal},
    'Unemployment Rate': {'category': 'labor', 'logic': logic_labor_normal},
    'Jobless Claims': {'category': 'labor', 'logic': logic_labor_inverse},
    'GDP': {'category': 'growth', 'logic': logic_growth},
    'ISM': {'category': 'growth', 'logic': logic_growth},
    'Retail Sales': {'category': 'growth', 'logic': logic_growth},
    'Federal Funds Rate': {'category': 'fed_policy', 'logic': logic_fed_policy},
    'Interest Rate': {'category': 'fed_policy', 'logic': logic_fed_policy},
    'FOMC': {'category': 'fed_policy', 'logic': logic_fed_policy},
    'Housing Starts': {'category': 'housing', 'logic': logic_housing},
    'Building Permits': {'category': 'housing', 'logic': logic_housing},
}

def classify_event(event_name: str) -> dict | None:
    """
    Returns the category and direction_logic for a given event name, or None if unrecognized.
    
    Args:
        event_name: The name of the event.
        
    Returns:
        dict with keys 'category' and 'direction_logic' (callable), or None.
    """
    for key, val in EVENT_CATEGORIES.items():
        if key.lower() in event_name.lower():
            return {
                'category': val['category'],
                'direction_logic': val['logic']
            }
    return None

def get_bias(event_name: str, actual: float, forecast: float, previous: float) -> tuple[str, float]:
    """
    Returns (bias: 'BUY'|'SELL'|'SKIP', confidence: float 0-1).
    
    Args:
        event_name: The name of the event.
        actual: The actual reported value.
        forecast: The forecasted value.
        previous: The previously reported value.
        
    Returns:
        Tuple containing bias and confidence.
    """
    if actual is None or forecast is None or math.isnan(actual) or math.isnan(forecast) or actual == forecast:
        return ('SKIP', 0.0)
        
    classification = classify_event(event_name)
    if not classification:
        return ('SKIP', 0.0)
        
    logic_fn = classification['direction_logic']
    impact = logic_fn(actual, forecast, previous)
    
    if impact == 'bullish_gold':
        bias = 'BUY'
    elif impact == 'bearish_gold':
        bias = 'SELL'
    else:
        bias = 'SKIP'
        
    # Calculate confidence based on abs(actual - forecast) / abs(previous)
    if previous is not None and not math.isnan(previous) and previous != 0:
        surprise = abs(actual - forecast)
        confidence = surprise / abs(previous)
        confidence = min(confidence, 1.0)
    else:
        confidence = 0.5
        
    if bias == 'SKIP':
        confidence = 0.0
        
    return (bias, confidence)
