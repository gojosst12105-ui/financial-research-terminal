"""News data fetching and aggregation service."""

import aiohttp
import asyncio
from typing import List, Dict, Optional
from datetime import datetime
import logging
from app.config import get_settings
from app.schemas import NewsArticle, SentimentEnum

logger = logging.getLogger(__name__)
settings = get_settings()


class NewsService:
    """Service for fetching financial news from multiple sources."""

    def __init__(self):
        self.finnhub_key = settings.finnhub_api_key
        self.newsapi_key = settings.newsapi_api_key
        self.marketaux_key = settings.marketaux_api_key

    async def fetch_company_news_finnhub(self, symbol: str, limit: int = 15) -> List[NewsArticle]:
        """Fetch company-specific news from Finnhub API."""
        if not self.finnhub_key:
            logger.warning("Finnhub API key not configured")
            return []

        url = f"https://finnhub.io/api/v1/company-news"
        params = {
            "symbol": symbol,
            "limit": limit,
            "token": self.finnhub_key
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        return self._parse_finnhub_news(data)
                    else:
                        logger.error(f"Finnhub API error: {response.status}")
                        return []
        except asyncio.TimeoutError:
            logger.error("Finnhub API request timeout")
            return []
        except Exception as e:
            logger.error(f"Error fetching Finnhub news: {str(e)}")
            return []

    async def fetch_company_news_newsapi(self, symbol: str, limit: int = 15) -> List[NewsArticle]:
        """Fetch company news from NewsAPI."""
        if not self.newsapi_key:
            logger.warning("NewsAPI key not configured")
            return []

        url = "https://newsapi.org/v2/everything"
        params = {
            "q": symbol,
            "sortBy": "publishedAt",
            "pageSize": limit,
            "apiKey": self.newsapi_key,
            "language": "en"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        return self._parse_newsapi_news(data)
                    else:
                        logger.error(f"NewsAPI error: {response.status}")
                        return []
        except asyncio.TimeoutError:
            logger.error("NewsAPI request timeout")
            return []
        except Exception as e:
            logger.error(f"Error fetching NewsAPI news: {str(e)}")
            return []

    async def fetch_market_news(self, limit: int = 10) -> List[NewsArticle]:
        """Fetch general market/financial news."""
        if not self.newsapi_key:
            logger.warning("NewsAPI key not configured for market news")
            return []

        url = "https://newsapi.org/v2/top-headlines"
        params = {
            "category": "business",
            "sortBy": "publishedAt",
            "pageSize": limit,
            "apiKey": self.newsapi_key,
            "language": "en"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        return self._parse_newsapi_news(data)
                    else:
                        logger.error(f"Market news API error: {response.status}")
                        return []
        except asyncio.TimeoutError:
            logger.error("Market news API request timeout")
            return []
        except Exception as e:
            logger.error(f"Error fetching market news: {str(e)}")
            return []

    def _parse_finnhub_news(self, data: dict) -> List[NewsArticle]:
        """Parse Finnhub API response."""
        articles = []
        try:
            for item in data:
                article = NewsArticle(
                    title=item.get("headline", ""),
                    source=item.get("source", "Unknown"),
                    summary=item.get("summary", ""),
                    url=item.get("url", ""),
                    published_at=datetime.fromtimestamp(item.get("datetime", 0)),
                    sentiment=self._detect_sentiment(item.get("sentiment", 0)),
                    image_url=item.get("image", ""),
                    category=item.get("category", "")
                )
                articles.append(article)
        except Exception as e:
            logger.error(f"Error parsing Finnhub news: {str(e)}")
        
        return articles

    def _parse_newsapi_news(self, data: dict) -> List[NewsArticle]:
        """Parse NewsAPI response."""
        articles = []
        try:
            for item in data.get("articles", []):
                article = NewsArticle(
                    title=item.get("title", ""),
                    source=item.get("source", {}).get("name", "Unknown"),
                    summary=item.get("description", ""),
                    url=item.get("url", ""),
                    published_at=datetime.fromisoformat(item.get("publishedAt", "").replace("Z", "+00:00")),
                    sentiment=SentimentEnum.UNKNOWN,
                    image_url=item.get("urlToImage", ""),
                    category="general"
                )
                articles.append(article)
        except Exception as e:
            logger.error(f"Error parsing NewsAPI news: {str(e)}")
        
        return articles

    def _detect_sentiment(self, sentiment_score: float) -> SentimentEnum:
        """Convert sentiment score to enum."""
        if sentiment_score > 0.1:
            return SentimentEnum.BULLISH
        elif sentiment_score < -0.1:
            return SentimentEnum.BEARISH
        else:
            return SentimentEnum.NEUTRAL

    async def get_news_for_symbol(self, symbol: str, limit: int = 15) -> tuple[List[NewsArticle], List[NewsArticle]]:
        """
        Fetch news for a symbol from multiple sources concurrently.
        Returns tuple of (company_news, market_news)
        """
        # Run both requests concurrently
        company_tasks = [
            self.fetch_company_news_finnhub(symbol, limit),
            self.fetch_company_news_newsapi(symbol, limit)
        ]
        market_task = self.fetch_market_news(5)

        company_results = await asyncio.gather(*company_tasks)
        market_news = await market_task

        # Merge company news from multiple sources and deduplicate
        all_company_news = []
        seen_urls = set()

        for news_list in company_results:
            for article in news_list:
                if article.url not in seen_urls:
                    all_company_news.append(article)
                    seen_urls.add(article.url)

        # Sort by published_at and limit
        all_company_news.sort(key=lambda x: x.published_at, reverse=True)
        all_company_news = all_company_news[:limit]

        return all_company_news, market_news


# Global instance
news_service = NewsService()
