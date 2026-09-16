"""
AI Advisory Bounded Context.
Blends mathematical optimization (MPT) with probabilistic AI sentiment analysis.
"""

from src.ai_advisory.profiling import RiskProfilingEngine, UserRiskProfile, RiskCategory
from src.ai_advisory.sentiment import LLMSentimentEngine, AssetSentiment
from src.ai_advisory.optimization import PortfolioOptimizer, OptimizationError

__all__ = [
    "RiskProfilingEngine",
    "UserRiskProfile",
    "RiskCategory",
    "LLMSentimentEngine",
    "AssetSentiment",
    "PortfolioOptimizer",
    "OptimizationError",
]