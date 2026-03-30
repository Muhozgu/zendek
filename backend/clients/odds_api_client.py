"""
clients/odds_api_client.py
--------------------------
Client for The Odds API (https://the-odds-api.com).

Handles all HTTP communication, rate-limit tracking,
caching, and structured error handling so the rest of
the app can stay clean.
"""

from __future__ import annotations

import os
import time
import logging
from typing import Any, Optional
from dataclasses import dataclass, field

import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

BASE_URL = "https://api.the-odds-api.com/v4"

# The Odds API sport keys we support
SPORT_KEYS: dict[str, str] = {
    "nba":       "basketball_nba",
    "nfl":       "americanfootball_nfl",
    "ncaaf":     "americanfootball_ncaaf",
    "mlb":       "baseball_mlb",
    "nhl":       "icehockey_nhl",
    "epl":       "soccer_epl",
    "la_liga":   "soccer_spain_la_liga",
    "ucl":       "soccer_uefa_champs_league",
    "mls":       "soccer_usa_mls",
    "tennis":    "tennis_atp_french_open",
    "ufc":       "mma_mixed_martial_arts",
}

# Default bookmakers to pull — covers US and major international books
DEFAULT_BOOKMAKERS = "fanduel,draftkings,betmgm,caesars,pointsbet,bovada,betonlineag"


# ──────────────────────────────────────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class RateLimitInfo:
    """Tracks remaining API quota from response headers."""
    requests_remaining: int = -1
    requests_used: int = -1
    requests_last: int = -1

    def update(self, headers: dict) -> None:
        self.requests_remaining = int(headers.get("x-requests-remaining", -1))
        self.requests_used      = int(headers.get("x-requests-used", -1))
        self.requests_last      = int(headers.get("x-requests-last", -1))

    def __str__(self) -> str:
        return (
            f"Quota — used: {self.requests_used} | "
            f"last call cost: {self.requests_last} | "
            f"remaining: {self.requests_remaining}"
        )


@dataclass
class OddsAPIError(Exception):
    """Structured error from the Odds API."""
    status_code: int
    message: str

    def __str__(self) -> str:
        return f"OddsAPIError [{self.status_code}]: {self.message}"


# ──────────────────────────────────────────────────────────────────────────────
# Simple in-memory cache
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class _CacheEntry:
    data: Any
    expires_at: float


class _SimpleCache:
    """TTL-based in-memory cache to avoid hammering the API on repeated queries."""

    def __init__(self) -> None:
        self._store: dict[str, _CacheEntry] = {}

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry and time.time() < entry.expires_at:
            return entry.data
        return None

    def set(self, key: str, data: Any, ttl: int = 120) -> None:
        self._store[key] = _CacheEntry(data=data, expires_at=time.time() + ttl)

    def clear(self) -> None:
        self._store.clear()


# ──────────────────────────────────────────────────────────────────────────────
# Main Client
# ──────────────────────────────────────────────────────────────────────────────

class OddsAPIClient:
    """
    Thread-safe client for The Odds API.

    Usage
    -----
    client = OddsAPIClient()
    games   = client.get_odds("nba")
    sports  = client.get_sports()
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        region: str = "us",
        odds_format: str = "american",
        cache_ttl: int = 120,       # seconds — 2-min default keeps quota sane
        timeout: int = 10,
    ) -> None:
        self.api_key     = api_key or os.getenv("ODDS_API_KEY", "")
        self.region      = region or os.getenv("ODDS_REGION", "us")
        self.odds_format = odds_format or os.getenv("ODDS_FORMAT", "american")
        self.timeout     = timeout
        self.cache_ttl   = cache_ttl
        self.rate_limit  = RateLimitInfo()
        self._cache      = _SimpleCache()
        self._session    = requests.Session()
        self._session.headers.update({"Accept": "application/json"})

        if not self.api_key:
            raise ValueError(
                "ODDS_API_KEY is not set. Add it to your .env file or "
                "pass api_key= to OddsAPIClient()."
            )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get(self, endpoint: str, params: dict) -> Any:
        """Execute a GET request, update rate-limit info, and handle errors."""
        params["apiKey"] = self.api_key
        url = f"{BASE_URL}/{endpoint}"

        try:
            resp = self._session.get(url, params=params, timeout=self.timeout)
        except requests.exceptions.ConnectionError as exc:
            raise OddsAPIError(0, f"Network error — are you online? ({exc})") from exc
        except requests.exceptions.Timeout as exc:
            raise OddsAPIError(0, f"Request timed out after {self.timeout}s") from exc

        self.rate_limit.update(resp.headers)

        if resp.status_code == 401:
            raise OddsAPIError(401, "Invalid API key. Check ODDS_API_KEY in your .env.")
        if resp.status_code == 422:
            raise OddsAPIError(422, f"Invalid parameters: {resp.text}")
        if resp.status_code == 429:
            raise OddsAPIError(429, "Rate limit exceeded — try again later or upgrade plan.")
        if not resp.ok:
            raise OddsAPIError(resp.status_code, resp.text)

        logger.debug("Odds API: %s | %s", url, self.rate_limit)
        return resp.json()

    def _sport_key(self, sport: str) -> str:
        """Resolve a short sport alias to its API key, or pass through verbatim."""
        key = SPORT_KEYS.get(sport.lower(), sport)
        if not key:
            available = ", ".join(SPORT_KEYS.keys())
            raise ValueError(
                f"Unknown sport '{sport}'. Available aliases: {available}"
            )
        return key

    # ── Public API ────────────────────────────────────────────────────────────

    def get_sports(self, all_sports: bool = False) -> list[dict]:
        """
        Return all available sports/leagues.

        Parameters
        ----------
        all_sports : bool
            If True, includes sports with no upcoming events.
        """
        cache_key = f"sports:{all_sports}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        data = self._get("sports", {"all": str(all_sports).lower()})
        self._cache.set(cache_key, data, ttl=300)   # sports list changes rarely
        return data

    def get_odds(
        self,
        sport: str,
        markets: str = "h2h",                       # h2h | spreads | totals
        bookmakers: Optional[str] = None,
        event_ids: Optional[list[str]] = None,
    ) -> list[dict]:
        """
        Fetch live/upcoming odds for a sport.

        Parameters
        ----------
        sport      : short alias (nba, nfl, epl …) or raw API sport key
        markets    : comma-separated market names
        bookmakers : comma-separated bookmaker IDs (overrides default set)
        event_ids  : optional list to fetch specific events only

        Returns
        -------
        List of event dicts, each containing bookmaker odds.
        """
        sport_key = self._sport_key(sport)
        cache_key = f"odds:{sport_key}:{markets}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        params: dict[str, Any] = {
            "regions":    self.region,
            "markets":    markets,
            "oddsFormat": self.odds_format,
            "bookmakers": bookmakers or DEFAULT_BOOKMAKERS,
        }
        if event_ids:
            params["eventIds"] = ",".join(event_ids)

        data = self._get(f"sports/{sport_key}/odds", params)
        self._cache.set(cache_key, data, ttl=self.cache_ttl)
        return data

    def get_scores(self, sport: str, days_from: int = 1) -> list[dict]:
        """
        Fetch recent scores / live game state.

        Parameters
        ----------
        days_from : how many days back to include completed games (1–3)
        """
        sport_key = self._sport_key(sport)
        cache_key = f"scores:{sport_key}:{days_from}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        data = self._get(
            f"sports/{sport_key}/scores",
            {"daysFrom": days_from}
        )
        self._cache.set(cache_key, data, ttl=30)    # scores update frequently
        return data

    def get_events(self, sport: str) -> list[dict]:
        """Return upcoming event IDs and metadata (no odds)."""
        sport_key = self._sport_key(sport)
        cache_key = f"events:{sport_key}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        data = self._get(f"sports/{sport_key}/events", {})
        self._cache.set(cache_key, data, ttl=120)
        return data

    def quota_status(self) -> str:
        """Human-readable quota status string."""
        return str(self.rate_limit)

    def clear_cache(self) -> None:
        """Force-clear the local cache (useful in testing)."""
        self._cache.clear()
        logger.info("Cache cleared.")