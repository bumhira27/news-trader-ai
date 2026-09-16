"""
Module for computing raw and normalized surprises from economic data releases.
"""

def compute_surprise(actual: float, forecast: float) -> float:
    """
    Computes the raw surprise (actual - forecast).
    
    Args:
        actual: The actual reported value.
        forecast: The forecasted value.
        
    Returns:
        The raw surprise.
    """
    return actual - forecast

def compute_normalized_surprise(actual: float, forecast: float, historical_std: float) -> float:
    """
    Computes a z-score style normalized surprise.
    
    Args:
        actual: The actual reported value.
        forecast: The forecasted value.
        historical_std: The historical standard deviation of the surprises.
        
    Returns:
        The normalized surprise.
    """
    if historical_std == 0:
        return 0.0
    return (actual - forecast) / historical_std

def score_surprise(actual: float, forecast: float, previous: float, historical_std: float | None = None) -> float:
    """
    Computes a surprise score clamped between -5 and +5.
    
    Args:
        actual: The actual reported value.
        forecast: The forecasted value.
        previous: The previously reported value.
        historical_std: Optional historical standard deviation for z-score normalization.
        
    Returns:
        A score from -5.0 to +5.0.
    """
    if historical_std is not None and historical_std > 0:
        score = (actual - forecast) / historical_std * 2.5
    else:
        denominator = max(abs(forecast), 0.01)
        score = (actual - forecast) / denominator * 10.0
        
    # Clamp between -5 and 5
    return max(-5.0, min(5.0, score))
