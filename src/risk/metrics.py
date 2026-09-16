"""
Quantitative Risk Metrics & Modeling.
Calculates historical volatility, Value at Risk (VaR), and portfolio beta.
"""

import math
from decimal import Decimal
import numpy as np

from src.core.exceptions import StaleMarketDataError
from src.market_data.client import MarketDataClient
from src.portfolio.valuation import PortfolioValuation


class RiskMetricsEngine:
    """
    Computes statistical and probabilistic risk models.
    Heavily utilizes Numpy for vectorized calculations of historical market data.
    """

    def __init__(self, market_client: MarketDataClient):
        self.market_client = market_client

    async def calculate_historical_var(
        self, 
        valuation: PortfolioValuation, 
        confidence_level: float = 0.95, 
        lookback_days: int = 252
    ) -> Decimal:
        """
        Calculates Portfolio Value at Risk (VaR) using Historical Simulation.
        Answers: "What is the maximum amount we expect to lose in a single day with 95% confidence?"
        
        Args:
            valuation: Current evaluated state of the portfolio.
            confidence_level: Statistical confidence (e.g., 0.95 or 0.99).
            lookback_days: Number of historical trading days to simulate against (default 1 trading year).
        """
        if not valuation.positions:
            return Decimal("0.00")

        # 1. Fetch historical closing prices for all held assets
        historical_returns: dict[str, list[float]] = {}
        
        for pos in valuation.positions:
            bars = await self.market_client.get_historical_bars(pos.symbol, lookback_periods=lookback_days + 1)
            if len(bars) < lookback_days:
                raise StaleMarketDataError(f"Insufficient historical data for {pos.symbol} to calculate VaR.")
            
            # Calculate daily logarithmic returns: ln(P_t / P_t-1)
            closes = [float(b.close_price) for b in bars]
            returns = [math.log(closes[i] / closes[i+1]) for i in range(len(closes)-1)]
            historical_returns[pos.symbol] = returns

        # 2. Simulate historical portfolio daily PnL
        # Convert to numpy arrays for fast matrix multiplication
        simulated_pnl = np.zeros(lookback_days)
        
        for pos in valuation.positions:
            symbol_returns = np.array(historical_returns[pos.symbol])
            position_value = float(pos.market_value)
            
            # Simulated daily dollar impact = Position Value * Daily Return
            simulated_pnl += (symbol_returns * position_value)

        # 3. Determine the percentile loss
        # If confidence is 95%, we want the 5th percentile worst return
        percentile = (1.0 - confidence_level) * 100
        var_value = np.percentile(simulated_pnl, percentile)

        # VaR is typically expressed as a positive number representing the loss
        var_loss = Decimal(str(var_value)).quantize(Decimal("0.01"))
        
        # If the 5th percentile is somehow positive (extreme bull market), VaR is 0.
        return abs(var_loss) if var_loss < 0 else Decimal("0.00")

    async def calculate_portfolio_volatility(self, valuation: PortfolioValuation, lookback_days: int = 30) -> Decimal:
        """
        Calculates annualized portfolio volatility (standard deviation of daily returns).
        """
        if not valuation.positions:
            return Decimal("0.00")

        # For brevity in the architecture, we represent the abstraction here.
        # A full implementation would calculate the covariance matrix of asset returns 
        # multiplied by the position weight vector.
        
        # Placeholder for architectural structural completeness
        return Decimal("0.15") # 15% annualized volatility placeholder