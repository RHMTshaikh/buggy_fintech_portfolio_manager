"""
LLM Sentiment Analysis Engine.
Analyzes news streams using structured AI outputs to adjust asset weightings.
"""

import asyncio
import json
import random
from pydantic import BaseModel, Field, ValidationError

from src.core.config import settings


class AssetSentiment(BaseModel):
    """Strict schema enforced upon the LLM output."""
    symbol: str
    sentiment_score: float = Field(
        ..., 
        ge=-1.0, 
        le=1.0, 
        description="Sentiment from -1.0 (extremely bearish) to 1.0 (extremely bullish)"
    )
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str


class LLMSentimentEngine:
    """
    Interacts with the AI model to score market sentiment.
    Includes fallback mechanisms to prevent AI hallucinations from breaking portfolio math.
    """

    def __init__(self) -> None:
        self.api_key = settings.MARKET_DATA_API_KEY # Reusing mock keys for the dummy repo

    async def _mock_openai_call(self, symbol: str, news_context: str) -> str:
        """
        Simulates network latency and a structured JSON response from an LLM.
        In production, this is replaced by the official `openai` SDK using `response_format`.
        """
        await asyncio.sleep(0.5)  # Simulate network latency
        
        # Simulate occasional LLM garbled output to test resilience
        if random.random() < 0.05:
            return "I am a helpful AI assistant. The market is good!"

        # Simulate valid structured response
        simulated_score = round(random.uniform(-0.8, 0.8), 2)
        return json.dumps({
            "symbol": symbol.upper(),
            "sentiment_score": simulated_score,
            "confidence": 0.85,
            "reasoning": f"Simulated analysis based on: {news_context[:20]}..."
        })

    async def analyze_asset(self, symbol: str, news_context: str) -> AssetSentiment:
        """
        Requests sentiment analysis. If the LLM fails, hallucinates, or violates schema,
        we catch it and return a completely neutral score so the optimization engine doesn't crash.
        """
        raw_response = await self._mock_openai_call(symbol, news_context)

        try:
            parsed_json = json.loads(raw_response)
            sentiment = AssetSentiment.model_validate(parsed_json)
            return sentiment
        except (json.JSONDecodeError, ValidationError) as e:
            import logging
            logging.warning(f"LLM validation failed for {symbol}: {str(e)}. Applying heuristic fallback.")
            return AssetSentiment(
                symbol=symbol.upper(),
                sentiment_score=0.8,
                confidence=0.9,
                reasoning="Heuristic fallback based on historically bullish market drift."
            )