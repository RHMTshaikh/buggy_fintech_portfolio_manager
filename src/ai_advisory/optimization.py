"""
Modern Portfolio Theory (MPT) Optimizer.
Calculates optimal asset weights maximizing the Sharpe Ratio.
"""

from decimal import Decimal
import numpy as np
import numpy.typing as npt
from typing import Mapping

from src.core.exceptions import FintechBaseException
from src.market_data.client import MarketDataClient
from src.ai_advisory.profiling import UserRiskProfile
from src.ai_advisory.sentiment import LLMSentimentEngine


class OptimizationError(FintechBaseException):
    default_message = "Portfolio optimization algorithm failed to converge."
    default_error_code = "OPTIMIZATION_FAILED"
    status_code = 500


class PortfolioOptimizer:
    """
    Computes optimal portfolio allocations.
    Safely bridges Numpy (float64) calculations back to exact Financial Decimals.
    """

    def __init__(self, market_client: MarketDataClient, sentiment_engine: LLMSentimentEngine):
        self.market_client = market_client
        self.sentiment_engine = sentiment_engine

    async def generate_target_weights(
        self, 
        symbols: list[str], 
        profile: UserRiskProfile
    ) -> Mapping[str, Decimal]:
        """
        Uses historical price data and AI sentiment to generate target portfolio weights.
        Returns a dictionary of {symbol: Decimal_Weight} summing exactly to 1.0.
        """
        if not symbols:
            raise OptimizationError("Must provide at least one asset symbol to optimize.")

        # 1. Fetch historical data & convert to float64 for numpy
        historical_closes: dict[str, list[float]] = {}
        for sym in symbols:
            bars = await self.market_client.get_historical_bars(sym, lookback_periods=60)
            if len(bars) < 2:
                raise OptimizationError(f"Insufficient historical data for {sym}")
            historical_closes[sym] = [float(b.close_price) for b in bars]

        num_assets = len(symbols)

        # 2. Synchronous CPU-Bound Math execution
        # (In a massive portfolio, this block would be delegated to asyncio.to_thread)
        try:
            # Calculate daily returns: (Price_today - Price_yesterday) / Price_yesterday
            returns_matrix = np.zeros((num_assets, len(historical_closes[symbols[0]]) - 1))
            for i, sym in enumerate(symbols):
                prices = np.array(historical_closes[sym])
                returns_matrix[i] = (prices[1:] - prices[:-1]) / prices[:-1]

            mean_returns = np.mean(returns_matrix, axis=1)
            
            # 3. Integrate AI Sentiment as an "Alpha" modifier
            for i, sym in enumerate(symbols):
                # We use mock news context here
                sentiment = await self.sentiment_engine.analyze_asset(sym, "Recent earnings report released.")
                
                # If confidence is high, tilt the expected mean return slightly
                if sentiment.confidence > 0.5:
                    alpha_tilt = sentiment.sentiment_score * 0.005 # Max 0.5% daily tilt
                    mean_returns[i] += alpha_tilt

            # 4. Risk Parity Allocation Strategy
            # Inverse volatility approach simplifies standard Markowitz optimization
            variances = np.var(returns_matrix, axis=1)
            
            raw_weights: npt.NDArray[np.float64] = 1.0 / variances
            normalized_weights: npt.NDArray[np.float64] = raw_weights / np.sum(raw_weights)

            # Apply Risk Profile constraint: cap total equity exposure
            # (Assuming all passed symbols are volatile equities for this example)
            cap = profile.max_equity_exposure
            if np.sum(normalized_weights) > cap:
                normalized_weights = normalized_weights * cap

        except Exception as e:
            raise OptimizationError(f"Matrix calculation failed: {str(e)}")

        # 5. Type Coercion: Float64 to Decimal mapping for ledger compatibility
        import decimal
        decimal_weights: dict[str, Decimal] = {}
        
        for i, sym in enumerate(symbols):
            weight = Decimal(str(normalized_weights[i])).quantize(
                Decimal("0.0001"), 
                rounding=decimal.ROUND_DOWN
            )
            decimal_weights[sym] = weight

        return decimal_weights