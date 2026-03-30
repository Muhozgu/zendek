"""
tools/betting_tools.py
----------------------
Bankroll management, Kelly Criterion, value-bet identification,
parlay math, and responsible gambling utilities.

All functions are pure (no I/O, no API calls).
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class KellySizing:
    """Output of kelly_criterion()."""
    fraction:       float   # recommended fraction of bankroll (0–1)
    fraction_pct:   float   # same, as a percentage
    half_kelly:     float   # conservative half-Kelly fraction
    quarter_kelly:  float   # ultra-conservative quarter-Kelly
    edge:           float   # estimated edge
    fair_prob:      float
    decimal_odds:   float
    rationale:      str


@dataclass
class ValueBet:
    """A single identified value bet."""
    outcome:        str
    book:           str
    offered_odds:   float   # American
    decimal_odds:   float
    fair_prob:      float
    implied_prob:   float
    edge_pct:       float
    ev_per_dollar:  float
    kelly_fraction: float
    strength:       str     # "STRONG" | "MODERATE" | "WEAK"


# ──────────────────────────────────────────────────────────────────────────────
# Kelly Criterion
# ──────────────────────────────────────────────────────────────────────────────

def kelly_criterion(
    fair_prob:    float,
    decimal_odds: float,
    bankroll:     Optional[float] = None,
    kelly_fraction: float = 1.0,   # 1.0 = full Kelly, 0.5 = half, 0.25 = quarter
) -> KellySizing:
    """
    Calculate the optimal bet size using the Kelly Criterion.

    The Kelly formula: f* = (p * b - q) / b
      where:
        p  = estimated win probability
        q  = 1 - p (loss probability)
        b  = net odds (decimal_odds - 1)

    Parameters
    ----------
    fair_prob     : your estimated probability of winning (0–1)
    decimal_odds  : the decimal odds offered by the bookmaker
    bankroll      : optional — if provided, returns absolute dollar amounts
    kelly_fraction: fraction of full Kelly to use (0.5 recommended for safety)

    Returns
    -------
    KellySizing dataclass with full breakdown.
    """
    p = fair_prob
    q = 1 - p
    b = decimal_odds - 1      # net profit per unit staked

    if b <= 0:
        return KellySizing(
            fraction=0, fraction_pct=0, half_kelly=0, quarter_kelly=0,
            edge=0, fair_prob=p, decimal_odds=decimal_odds,
            rationale="Invalid odds — decimal must be > 1.0"
        )

    full_kelly = (p * b - q) / b

    # Cap at 25% of bankroll — never bet more than a quarter even with massive edge
    full_kelly = max(0.0, min(full_kelly, 0.25))
    half_k     = full_kelly * 0.5
    quarter_k  = full_kelly * 0.25
    applied    = full_kelly * kelly_fraction

    edge = p - (1 / decimal_odds)

    # Build rationale
    if full_kelly <= 0:
        rationale = "No edge detected — Kelly says do not bet."
    elif full_kelly < 0.02:
        rationale = f"Tiny edge ({edge*100:.1f}%) — consider skipping or quarter-Kelly only."
    elif full_kelly < 0.05:
        rationale = f"Moderate edge ({edge*100:.1f}%) — half-Kelly ({half_k*100:.1f}%) is prudent."
    else:
        rationale = (
            f"Strong edge ({edge*100:.1f}%) — recommended stake is "
            f"half-Kelly ({half_k*100:.1f}%) to reduce variance."
        )

    return KellySizing(
        fraction=round(applied, 4),
        fraction_pct=round(applied * 100, 2),
        half_kelly=round(half_k, 4),
        quarter_kelly=round(quarter_k, 4),
        edge=round(edge, 4),
        fair_prob=p,
        decimal_odds=decimal_odds,
        rationale=rationale,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Value bet identification
# ──────────────────────────────────────────────────────────────────────────────

def american_to_decimal(american: float) -> float:
    """American odds → decimal odds."""
    if american >= 100:
        return (american / 100) + 1
    return (100 / abs(american)) + 1


def american_to_implied_prob(american: float) -> float:
    if american >= 100:
        return 100 / (american + 100)
    return abs(american) / (abs(american) + 100)


def identify_value_bets(
    events_data: list[dict],       # parsed from OddsAnalyzer.best_available_odds()
    fair_probs: dict[str, float],  # {"Lakers": 0.58, "Celtics": 0.42}
    min_edge: float = 0.03,        # only flag bets with ≥3% edge
) -> list[ValueBet]:
    """
    Given bookmaker odds and your own estimated probabilities,
    return a list of value bets (where offered odds exceed fair value).

    Parameters
    ----------
    events_data  : list of {outcome_name, best_odds, book, decimal, implied_prob}
    fair_probs   : your model's probability estimates for each outcome
    min_edge     : minimum edge threshold to flag a value bet

    Returns
    -------
    Sorted list of ValueBet (highest edge first).
    """
    value_bets: list[ValueBet] = []

    for outcome_name, fair_p in fair_probs.items():
        # Find the best odds for this outcome
        match = next(
            (e for e in events_data if e.get("name") == outcome_name),
            None
        )
        if not match:
            continue

        offered  = match["odds"]            # American
        dec      = american_to_decimal(offered)
        imp_prob = american_to_implied_prob(offered)
        edge     = fair_p - imp_prob
        ev       = fair_p * (dec - 1) - (1 - fair_p)

        if edge < min_edge:
            continue

        kelly = kelly_criterion(fair_p, dec, kelly_fraction=0.5)

        if edge >= 0.08:
            strength = "STRONG"
        elif edge >= 0.04:
            strength = "MODERATE"
        else:
            strength = "WEAK"

        value_bets.append(ValueBet(
            outcome=outcome_name,
            book=match.get("book", "Unknown"),
            offered_odds=offered,
            decimal_odds=round(dec, 4),
            fair_prob=round(fair_p, 4),
            implied_prob=round(imp_prob, 4),
            edge_pct=round(edge * 100, 2),
            ev_per_dollar=round(ev, 4),
            kelly_fraction=kelly.half_kelly,
            strength=strength,
        ))

    value_bets.sort(key=lambda b: b.edge_pct, reverse=True)
    return value_bets


# ──────────────────────────────────────────────────────────────────────────────
# Parlay math
# ──────────────────────────────────────────────────────────────────────────────

def parlay_odds(legs: list[float], fmt: str = "american") -> dict:
    """
    Calculate the combined parlay odds for a list of individual legs.

    Parameters
    ----------
    legs : list of odds per leg (all same format)
    fmt  : "american" | "decimal"

    Returns
    -------
    {
      "decimal_odds": 6.45,
      "american_odds": +545,
      "implied_prob": 0.155,
      "num_legs": 3,
    }
    """
    if fmt == "american":
        decimals = [american_to_decimal(o) for o in legs]
    else:
        decimals = list(legs)

    combined_dec  = 1.0
    for d in decimals:
        combined_dec *= d

    combined_american = (
        (combined_dec - 1) * 100
        if combined_dec >= 2.0
        else -100 / (combined_dec - 1)
    )
    implied = 1.0 / combined_dec

    return {
        "decimal_odds":   round(combined_dec, 4),
        "american_odds":  round(combined_american, 0),
        "implied_prob":   round(implied, 4),
        "implied_prob_pct": round(implied * 100, 2),
        "num_legs":       len(legs),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Implied probability utilities
# ──────────────────────────────────────────────────────────────────────────────

def break_even_probability(decimal_odds: float) -> float:
    """Return the minimum win probability needed to profit at given odds."""
    return 1.0 / decimal_odds


def profit_on_win(stake: float, decimal_odds: float) -> float:
    """Net profit if the bet wins."""
    return stake * (decimal_odds - 1)


def payout_on_win(stake: float, decimal_odds: float) -> float:
    """Total return (stake + profit) if the bet wins."""
    return stake * decimal_odds


def expected_value(fair_prob: float, decimal_odds: float, stake: float = 1.0) -> float:
    """Expected monetary value of a bet over the long run."""
    win_amount  = profit_on_win(stake, decimal_odds)
    lose_amount = stake
    return fair_prob * win_amount - (1 - fair_prob) * lose_amount


# ──────────────────────────────────────────────────────────────────────────────
# Bankroll management
# ──────────────────────────────────────────────────────────────────────────────

def bankroll_summary(
    bankroll:      float,
    max_bet_pct:   float = 0.05,    # 5% flat-bet cap
    kelly_pct:     float = 0.02,    # example Kelly fraction
    num_bets_day:  int   = 3,
) -> dict:
    """
    Produce a responsible bankroll management summary.

    Parameters
    ----------
    bankroll      : total available bankroll in dollars
    max_bet_pct   : maximum single-bet size as fraction of bankroll
    kelly_pct     : Kelly-recommended fraction for a given bet
    num_bets_day  : how many bets you plan to place today

    Returns
    -------
    Dict with concrete dollar amounts and risk warnings.
    """
    flat_bet    = bankroll * max_bet_pct
    kelly_bet   = bankroll * kelly_pct
    daily_risk  = flat_bet * num_bets_day
    risk_ratio  = daily_risk / bankroll

    warnings = []
    if risk_ratio > 0.20:
        warnings.append("⚠️  Daily risk exceeds 20% of bankroll — very high risk.")
    if max_bet_pct > 0.10:
        warnings.append("⚠️  Single bet cap > 10% — consider reducing to 5% or less.")
    if num_bets_day > 5:
        warnings.append("⚠️  Placing 5+ bets per day increases variance significantly.")

    return {
        "bankroll":         bankroll,
        "flat_bet_5pct":    round(flat_bet, 2),
        "kelly_bet":        round(kelly_bet, 2),
        "daily_exposure":   round(daily_risk, 2),
        "daily_risk_pct":   round(risk_ratio * 100, 2),
        "warnings":         warnings,
        "recommendation":   (
            "Stick to 1–5% of bankroll per bet. "
            "Use half-Kelly for volatile edges. "
            "Never chase losses."
        ),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Responsible gambling
# ──────────────────────────────────────────────────────────────────────────────

RESPONSIBLE_GAMBLING_REMINDER = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ⚠️  RESPONSIBLE GAMBLING REMINDER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Sports betting involves real financial risk.
• Never bet more than you can afford to lose.
• Set strict limits and stick to them.
• Do not chase losses — accept variance as part of the game.
• This tool is for analysis only, not guaranteed profit advice.

If you or someone you know has a gambling problem:
  🇺🇸  National Problem Gambling Helpline: 1-800-522-4700
  🌐  www.ncpgambling.org
  💬  Text "HELPLINE" to 233369
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""


class BettingCalculator:
    """
    Convenience class that wraps the module-level functions
    for use via the CLI and LLM tool dispatch.
    """

    @staticmethod
    def kelly(fair_prob: float, american_odds: float) -> KellySizing:
        dec = american_to_decimal(american_odds)
        return kelly_criterion(fair_prob, dec, kelly_fraction=0.5)

    @staticmethod
    def parlay(*american_odds: float) -> dict:
        return parlay_odds(list(american_odds), fmt="american")

    @staticmethod
    def ev(fair_prob: float, american_odds: float, stake: float = 100.0) -> dict:
        dec = american_to_decimal(american_odds)
        return {
            "fair_prob":      fair_prob,
            "american_odds":  american_odds,
            "decimal_odds":   round(dec, 4),
            "stake":          stake,
            "expected_value": round(expected_value(fair_prob, dec, stake), 2),
            "break_even_prob": round(break_even_probability(dec) * 100, 2),
            "payout_if_win":  round(payout_on_win(stake, dec), 2),
        }

    @staticmethod
    def bankroll(bankroll: float, kelly_pct: float = 0.02, bets_today: int = 3) -> dict:
        return bankroll_summary(bankroll, kelly_pct=kelly_pct, num_bets_day=bets_today)

    @staticmethod
    def responsible_reminder() -> str:
        return RESPONSIBLE_GAMBLING_REMINDER