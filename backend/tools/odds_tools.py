"""
tools/odds_tools.py
-------------------
Pure analysis functions that operate on raw Odds API payloads.

All functions are stateless and return structured dicts / lists
that can be serialised to JSON or formatted for display.
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Outcome:
    """Single team/side outcome within a bookmaker's market."""
    name:  str
    price: float     # American odds integer or decimal float
    point: Optional[float] = None   # spread / total line


@dataclass
class BookmakerLine:
    """All markets offered by one bookmaker for one event."""
    bookmaker_key:   str
    bookmaker_title: str
    outcomes:        list[Outcome] = field(default_factory=list)


@dataclass
class EventOdds:
    """Parsed odds for a single game / event."""
    event_id:    str
    sport:       str
    home_team:   str
    away_team:   str
    commence_time: str
    markets:     dict[str, list[BookmakerLine]] = field(default_factory=dict)


# ──────────────────────────────────────────────────────────────────────────────
# Conversion helpers
# ──────────────────────────────────────────────────────────────────────────────

def american_to_decimal(american: float) -> float:
    """Convert American (moneyline) odds to European decimal odds."""
    if american >= 100:
        return (american / 100) + 1
    else:
        return (100 / abs(american)) + 1


def decimal_to_american(decimal: float) -> float:
    """Convert decimal odds to American odds."""
    if decimal >= 2.0:
        return (decimal - 1) * 100
    else:
        return -100 / (decimal - 1)


def american_to_implied_prob(american: float) -> float:
    """
    Convert American odds to raw implied probability (includes vig).

    Returns a value in [0, 1].
    """
    if american >= 100:
        return 100 / (american + 100)
    else:
        return abs(american) / (abs(american) + 100)


def decimal_to_implied_prob(decimal: float) -> float:
    """Convert decimal odds to implied probability."""
    if decimal <= 0:
        return 0.0
    return 1.0 / decimal


def remove_vig(probs: list[float]) -> list[float]:
    """
    Normalise a list of raw implied probabilities to sum to 1.0
    by dividing each by the overround (total implied probability).

    This gives the bookmaker's 'true' probability estimates
    after stripping their margin.
    """
    total = sum(probs)
    if total == 0:
        return probs
    return [p / total for p in probs]


def overround(probs: list[float]) -> float:
    """
    Calculate the bookmaker's overround (vig) as a percentage.

    e.g. 1.05 means the book takes a 5% margin.
    """
    return sum(probs)


# ──────────────────────────────────────────────────────────────────────────────
# Parser
# ──────────────────────────────────────────────────────────────────────────────

def parse_events(raw_events: list[dict]) -> list[EventOdds]:
    """
    Parse the raw JSON list from OddsAPIClient.get_odds()
    into typed EventOdds objects.
    """
    events: list[EventOdds] = []

    for ev in raw_events:
        event = EventOdds(
            event_id=ev.get("id", ""),
            sport=ev.get("sport_key", ""),
            home_team=ev.get("home_team", ""),
            away_team=ev.get("away_team", ""),
            commence_time=ev.get("commence_time", ""),
        )

        for bm in ev.get("bookmakers", []):
            for market in bm.get("markets", []):
                market_key = market.get("key", "")
                outcomes = [
                    Outcome(
                        name=o.get("name", ""),
                        price=o.get("price", 0.0),
                        point=o.get("point"),
                    )
                    for o in market.get("outcomes", [])
                ]
                line = BookmakerLine(
                    bookmaker_key=bm.get("key", ""),
                    bookmaker_title=bm.get("title", bm.get("key", "")),
                    outcomes=outcomes,
                )
                event.markets.setdefault(market_key, []).append(line)

        events.append(event)

    return events


# ──────────────────────────────────────────────────────────────────────────────
# OddsAnalyzer
# ──────────────────────────────────────────────────────────────────────────────

class OddsAnalyzer:
    """
    High-level analysis functions that operate on parsed EventOdds.

    All public methods return plain dicts/lists ready for display or
    injection into the LLM context.
    """

    # ── Best-line finder ─────────────────────────────────────────────────────

    @staticmethod
    def best_available_odds(event: EventOdds, market: str = "h2h") -> dict:
        """
        Find the best (highest) odds for each outcome across all bookmakers.

        Returns a dict keyed by outcome name:
        {
          "Lakers": {"best_odds": -110, "book": "FanDuel", "decimal": 1.91},
          "Celtics": {"best_odds": +120, "book": "DraftKings", "decimal": 2.20},
          ...
        }
        """
        bests: dict[str, dict] = {}
        lines = event.markets.get(market, [])

        for line in lines:
            for outcome in line.outcomes:
                dec = american_to_decimal(outcome.price)
                if outcome.name not in bests or dec > bests[outcome.name]["decimal"]:
                    bests[outcome.name] = {
                        "best_odds": outcome.price,
                        "book":      line.bookmaker_title,
                        "decimal":   round(dec, 4),
                        "implied_prob": round(american_to_implied_prob(outcome.price), 4),
                    }

        return bests

    # ── Odds comparison table ────────────────────────────────────────────────

    @staticmethod
    def odds_comparison_table(event: EventOdds, market: str = "h2h") -> list[dict]:
        """
        Build a cross-bookmaker comparison table for the given market.

        Returns a list of rows — one per bookmaker:
        [
          {
            "bookmaker": "FanDuel",
            "outcomes": [
              {"name": "Lakers", "odds": -110, "implied_prob": 52.38},
              {"name": "Celtics", "odds": +130, "implied_prob": 43.48},
            ],
            "overround": 1.0486,
            "vig_pct": 4.86,
          },
          ...
        ]
        """
        rows = []
        lines = event.markets.get(market, [])

        for line in lines:
            probs = [american_to_implied_prob(o.price) for o in line.outcomes]
            og = overround(probs)
            row = {
                "bookmaker": line.bookmaker_title,
                "outcomes": [
                    {
                        "name":         o.name,
                        "odds":         o.price,
                        "decimal":      round(american_to_decimal(o.price), 4),
                        "implied_prob": round(american_to_implied_prob(o.price) * 100, 2),
                        "point":        o.point,
                    }
                    for o in line.outcomes
                ],
                "overround": round(og, 4),
                "vig_pct":   round((og - 1) * 100, 2),
            }
            rows.append(row)

        # Sort by vig ascending — lowest vig book first
        rows.sort(key=lambda r: r["vig_pct"])
        return rows

    # ── Arbitrage / line-shopping ─────────────────────────────────────────────

    @staticmethod
    def detect_arbitrage(event: EventOdds, market: str = "h2h") -> Optional[dict]:
        """
        Check whether an arbitrage opportunity exists across bookmakers.

        An arb exists when the sum of the best implied probabilities
        for each side is less than 1.0 (total < 100%).

        Returns None if no arb, else:
        {
          "arb_exists": True,
          "profit_pct": 2.3,
          "sides": [
            {"outcome": "Lakers", "odds": -105, "book": "Bovada", "stake_pct": 51.2},
            {"outcome": "Celtics", "odds": +140, "book": "FanDuel", "stake_pct": 41.7},
          ]
        }
        """
        bests = OddsAnalyzer.best_available_odds(event, market)
        if not bests:
            return None

        total_implied = sum(v["implied_prob"] for v in bests.values())

        if total_implied >= 1.0:
            return None     # no arb

        profit_pct = round((1 - total_implied) * 100, 2)
        sides = [
            {
                "outcome":   name,
                "odds":      info["best_odds"],
                "book":      info["book"],
                # proportional stake allocation
                "stake_pct": round(info["implied_prob"] / total_implied * 100, 2),
            }
            for name, info in bests.items()
        ]

        return {
            "arb_exists":  True,
            "profit_pct":  profit_pct,
            "total_implied_prob": round(total_implied * 100, 2),
            "sides":       sides,
        }

    # ── Fair value & edge calculation ────────────────────────────────────────

    @staticmethod
    def calculate_edge(
        fair_prob: float,
        market_odds: float,
        odds_format: str = "american",
    ) -> dict:
        """
        Given your estimated fair probability for an outcome
        and the available market odds, calculate your edge.

        Parameters
        ----------
        fair_prob    : your estimated true probability (0–1)
        market_odds  : the odds you can get (American or decimal)
        odds_format  : "american" | "decimal"

        Returns
        -------
        {
          "fair_prob": 0.55,
          "market_implied_prob": 0.476,
          "edge_pct": 7.4,
          "expected_value": 0.148,   # per $1 wagered
          "is_value_bet": True,
        }
        """
        if odds_format == "american":
            dec = american_to_decimal(market_odds)
        else:
            dec = market_odds

        market_imp = decimal_to_implied_prob(dec)
        edge = fair_prob - market_imp
        ev   = fair_prob * (dec - 1) - (1 - fair_prob)

        return {
            "fair_prob":           round(fair_prob, 4),
            "market_implied_prob": round(market_imp, 4),
            "edge_pct":            round(edge * 100, 2),
            "expected_value":      round(ev, 4),
            "is_value_bet":        edge > 0,
            "decimal_odds":        round(dec, 4),
        }

    # ── Summary formatter for LLM context injection ──────────────────────────

    @staticmethod
    def format_for_llm(events: list[EventOdds], market: str = "h2h") -> str:
        """
        Produce a structured plain-text summary of events + odds
        for injection into the Groq context window.
        """
        if not events:
            return "No events found."

        lines = []
        for ev in events[:10]:     # cap at 10 to avoid token bloat
            lines.append(
                f"\n{'='*60}\n"
                f"GAME: {ev.away_team} @ {ev.home_team}\n"
                f"ID:   {ev.event_id}\n"
                f"TIME: {ev.commence_time}\n"
            )

            comparison = OddsAnalyzer.odds_comparison_table(ev, market)
            if not comparison:
                lines.append("  [No odds available]\n")
                continue

            # Header
            outcome_names = [o["name"] for o in comparison[0]["outcomes"]] if comparison else []
            header = f"  {'BOOKMAKER':<20}" + "".join(f"{n:<18}" for n in outcome_names) + "VIG%"
            lines.append(header)
            lines.append("  " + "-" * (len(header) - 2))

            for row in comparison:
                cols = f"  {row['bookmaker']:<20}"
                for o in row["outcomes"]:
                    odds_str = f"{o['odds']:+.0f} ({o['implied_prob']:.1f}%)"
                    cols += f"{odds_str:<18}"
                cols += f"{row['vig_pct']:.2f}%"
                lines.append(cols)

            # Best odds and arb check
            bests = OddsAnalyzer.best_available_odds(ev, market)
            lines.append("\n  BEST AVAILABLE:")
            for name, info in bests.items():
                lines.append(
                    f"    {name}: {info['best_odds']:+.0f} @ {info['book']} "
                    f"(implied {info['implied_prob']*100:.1f}%)"
                )

            arb = OddsAnalyzer.detect_arbitrage(ev, market)
            if arb:
                lines.append(f"\n  ⚡ ARBITRAGE DETECTED — {arb['profit_pct']:.2f}% profit lock")

        return "\n".join(lines)