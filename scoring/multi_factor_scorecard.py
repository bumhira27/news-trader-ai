
import typing

class MacroScorecard:
    """
    Implements a fundamental macro scorecard for predicting XAUUSD direction 
    *BEFORE* the news is released.
    Uses Forecast vs Previous, rather than Actual vs Forecast.
    """
    
    def score_inflation_expectation(self, forecast: float, previous: float) -> float:
        """
        Score inflation based on CPI/PCE forecast vs previous.
        - If forecast > previous (inflation expected to rise): bearish gold (-1.5)
        - If forecast < previous (inflation expected to cool): bullish gold (+1.5)
        """
        if forecast > previous:
            return -1.5
        elif forecast < previous:
            return 1.5
        return 0.0
    
    def score_labor_expectation(self, nfp_forecast: float | None, nfp_previous: float | None, claims_forecast: float | None, claims_previous: float | None) -> float:
        """
        Score labor market strength based on expectations.
        - Strong labor expected = bearish gold (-1)
        - Weak labor expected = bullish gold (+1)
        """
        score = 0.0
        strong = False
        weak = False
        
        if nfp_forecast is not None and nfp_previous is not None:
            if nfp_forecast > nfp_previous: strong = True
            elif nfp_forecast < nfp_previous: weak = True
                
        if claims_forecast is not None and claims_previous is not None:
            if claims_forecast < claims_previous: strong = True
            elif claims_forecast > claims_previous: weak = True
                
        if strong and not weak: score = -1.0
        elif weak and not strong: score = 1.0
        return score

    def score_growth_expectation(self, forecast: float, previous: float) -> float:
        """
        Score economic growth (ISM, Retail Sales) expectations.
        - Higher growth expected = bearish gold (-1)
        - Lower growth expected = bullish gold (+1)
        """
        if forecast > previous: return -1.0
        elif forecast < previous: return 1.0
        return 0.0
        
    def score_rate_expectations(self, current_rate: float, expected_rate: float) -> float:
        """
        Score based on rate expectations (FOMC).
        - If expected_rate > current_rate (hike expected): bearish gold (-2)
        - If expected_rate < current_rate (cut expected): bullish gold (+2)
        """
        if expected_rate > current_rate: return -2.0
        elif expected_rate < current_rate: return 2.0
        return 0.0
        
    def score_yields_factor(self, us10y_current: float) -> float:
        """
        Score based on US 10Y yields. 
        As a proxy, if yield > 4.5% (high), bearish. If yield < 3.8% (low), bullish.
        """
        if us10y_current > 4.5: return -1.0
        elif us10y_current < 3.8: return 1.0
        return 0.0
        
    def score_safe_haven(self) -> float:
        return 0.5
        
    def generate_pre_release_scorecard(self, **kwargs) -> dict:
        """
        Generate scorecard strictly from pre-release info (forecasts and macro).
        """
        factors = {}
        
        if "cpi_forecast" in kwargs and "cpi_previous" in kwargs:
            factors["inflation"] = self.score_inflation_expectation(kwargs["cpi_forecast"], kwargs["cpi_previous"])
            
        if "nfp_forecast" in kwargs or "claims_forecast" in kwargs:
            factors["labor"] = self.score_labor_expectation(
                kwargs.get("nfp_forecast"), kwargs.get("nfp_previous"),
                kwargs.get("claims_forecast"), kwargs.get("claims_previous")
            )

        if "growth_forecast" in kwargs and "growth_previous" in kwargs:
            factors["growth"] = self.score_growth_expectation(kwargs["growth_forecast"], kwargs["growth_previous"])
            
        if "current_rate" in kwargs and "expected_rate" in kwargs:
            factors["rate_expectations"] = self.score_rate_expectations(kwargs["current_rate"], kwargs["expected_rate"])
            
        if "us10y_yield" in kwargs:
            factors["yields"] = self.score_yields_factor(kwargs["us10y_yield"])
            
        factors["safe_haven"] = self.score_safe_haven()
        
        total_score = sum(factors.values())
        if total_score < -1.0: bias = "SELL"
        elif total_score > 1.0: bias = "BUY"
        else: bias = "SKIP"
            
        return {
            "factors": factors,
            "total_score": total_score,
            "bias": bias
        }

