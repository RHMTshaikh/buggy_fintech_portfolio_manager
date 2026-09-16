"""
User Risk Profiling Engine.
Maps user demographics and financial goals to strict mathematical volatility constraints.
"""

import enum
from pydantic import BaseModel, Field


class RiskCategory(str, enum.Enum):
    CONSERVATIVE = "CONSERVATIVE"
    MODERATE = "MODERATE"
    AGGRESSIVE = "AGGRESSIVE"


class UserRiskProfile(BaseModel):
    """The strict mathematical boundaries derived from the user's questionnaire."""
    category: RiskCategory
    max_equity_exposure: float = Field(..., description="Maximum allowed weight in volatile assets (0.0 to 1.0)")
    target_volatility: float = Field(..., description="Target annualized portfolio volatility")


class RiskProfilingEngine:
    """
    Evaluates user metrics to assign algorithmic trading guardrails.
    """

    def evaluate_user_risk(self, age: int, investment_horizon_years: int, liquid_net_worth: float) -> UserRiskProfile:
        """
        Determines the risk profile based on standard financial planning heuristics.
        """
        score = 0
        
        # Horizon is the strongest predictor of risk tolerance
        if investment_horizon_years > 10:
            score += 5
        elif investment_horizon_years > 3:
            score += 3
        else:
            score += 1

        # Age penalty (younger = more aggressive)
        if age < 35:
            score += 3
        elif age < 55:
            score += 2
        else:
            score += 1

        if score >= 7:
            return UserRiskProfile(
                category=RiskCategory.AGGRESSIVE,
                max_equity_exposure=0.90,
                target_volatility=0.20
            )
        elif score >= 5:
            return UserRiskProfile(
                category=RiskCategory.MODERATE,
                max_equity_exposure=0.60,
                target_volatility=0.12
            )
        else:
            return UserRiskProfile(
                category=RiskCategory.CONSERVATIVE,
                max_equity_exposure=0.30,
                target_volatility=0.05
            )