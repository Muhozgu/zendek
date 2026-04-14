"""
api.py  —  BetIQ FastAPI backend (production-ready)
Run locally:  uvicorn api:app --reload --port 8000
Deploy:       render.com — see render.yaml
"""

from __future__ import annotations

import os
import json
import asyncio
import logging
from typing import AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from clients.odds_api_client import OddsAPIClient, OddsAPIError, SPORT_KEYS
from clients.groq_client import GroqChatClient
from tools.odds_tools import OddsAnalyzer, parse_events
from tools.betting_tools import (
    BettingCalculator,
    american_to_decimal,
    parlay_odds,
    kelly_criterion,
    expected_value,
    bankroll_summary,
)

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── CORS origins ──────────────────────────────────────────────────────────────
# Add your Vercel URL here. Wildcards are blocked by browsers for credentialed
# requests, so list every origin explicitly.

ALLOWED_ORIGINS = [
    "http://localhost:5173",          # Vite dev server
    "http://localhost:4173",          # Vite preview
    "http://localhost:3000",          # fallback
    os.getenv("FRONTEND_URL", ""),    # set this in Render dashboard → your Vercel URL
                                      # e.g. https://betiq.vercel.app
]

# Filter out empty strings (when env var not set)
ALLOWED_ORIGINS = [o for o in ALLOWED_ORIGINS if o]

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="BetIQ API",
    description="Sports Betting AI — Groq Llama 3.3 + The Odds API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Singletons ────────────────────────────────────────────────────────────────

_odds = OddsAPIClient()
_groq = GroqChatClient()


# ── Request / Response models ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    history: list[dict] = Field(default_factory=list)
    sport:   Optional[str] = None
    market:  str = "h2h"


class EVRequest(BaseModel):
    fair_prob:     float = Field(..., ge=0.01, le=0.99)
    american_odds: float
    stake:         float = 100.0


class KellyRequest(BaseModel):
    fair_prob:     float = Field(..., ge=0.01, le=0.99)
    american_odds: float
    bankroll:      float = 1000.0


class ParlayRequest(BaseModel):
    legs: list[float] = Field(..., min_length=2)


class BankrollRequest(BaseModel):
    bankroll:   float
    bets_today: int = 3


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_odds_context(sport: str, market: str = "h2h") -> Optional[str]:
    try:
        raw    = _odds.get_odds(sport, markets=market)
        events = parse_events(raw)
        return OddsAnalyzer.format_for_llm(events, market)
    except OddsAPIError:
        return None


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "BetIQ API"}


@app.get("/sports")
def list_sports():
    return {"sports": SPORT_KEYS}


@app.get("/odds/{sport}")
def get_odds(
    sport:     str,
    market:    str = Query("h2h", enum=["h2h", "spreads", "totals"]),
    max_games: int = Query(10, ge=1, le=20),
):
    try:
        raw    = _odds.get_odds(sport, markets=market)
        events = parse_events(raw)
    except OddsAPIError as e:
        raise HTTPException(status_code=e.status_code or 502, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    result = []
    for ev in events[:max_games]:
        comparison = OddsAnalyzer.odds_comparison_table(ev, market)
        best       = OddsAnalyzer.best_available_odds(ev, market)
        arb        = OddsAnalyzer.detect_arbitrage(ev, market)
        result.append({
            "event_id":      ev.event_id,
            "sport":         ev.sport,
            "home_team":     ev.home_team,
            "away_team":     ev.away_team,
            "commence_time": ev.commence_time,
            "market":        market,
            "bookmakers":    comparison,
            "best_odds":     best,
            "arbitrage":     arb,
        })

    return {
        "sport":       sport,
        "market":      market,
        "event_count": len(events),
        "events":      result,
        "quota":       _odds.quota_status(),
    }


@app.post("/chat")
def chat(req: ChatRequest):
    context = _load_odds_context(req.sport, req.market) if req.sport else None
    reply, updated_history = _groq.chat_with_history(
        req.message, req.history, context,
    )
    return {"reply": reply, "history": updated_history}


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """
    Server-Sent Events streaming endpoint.
    Each event:   data: {"chunk": "..."}\n\n
    Final event:  data: [DONE]\n\n
    """
    context = _load_odds_context(req.sport, req.market) if req.sport else None

    async def event_generator() -> AsyncGenerator[str, None]:
        gen = _groq.stream(req.message, history=req.history, context=context)
        for chunk in gen:
            yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            await asyncio.sleep(0)
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/analyze/{sport}")
def analyze(
    sport:       str,
    team_filter: Optional[str] = Query(None),
    market:      str = Query("h2h"),
):
    try:
        raw    = _odds.get_odds(sport, markets=market)
        events = parse_events(raw)
    except OddsAPIError as e:
        raise HTTPException(status_code=e.status_code or 502, detail=str(e))

    if team_filter:
        tf     = team_filter.lower()
        events = [e for e in events
                  if tf in e.home_team.lower() or tf in e.away_team.lower()]

    if not events:
        raise HTTPException(status_code=404, detail="No matching events found.")

    context  = OddsAnalyzer.format_for_llm(events, market)
    prompt   = (
        f"Analyze {'this game' if len(events)==1 else f'these {len(events)} upcoming games'}. "
        "For each: implied probabilities, vig, line discrepancies, best odds, value/arb flags."
    )
    analysis = _groq.chat(prompt, context=context)
    return {"sport": sport, "market": market, "events_analyzed": len(events), "analysis": analysis}


@app.post("/calculate/ev")
def calculate_ev(req: EVRequest):
    dec = american_to_decimal(req.american_odds)
    ev  = expected_value(req.fair_prob, dec, req.stake)
    imp = 1.0 / dec
    return {
        "fair_prob":           req.fair_prob,
        "american_odds":       req.american_odds,
        "decimal_odds":        round(dec, 4),
        "market_implied_prob": round(imp, 4),
        "stake":               req.stake,
        "expected_value":      round(ev, 2),
        "payout_if_win":       round(req.stake * dec, 2),
        "is_value_bet":        ev > 0,
        "break_even_prob":     round(imp * 100, 2),
    }


@app.post("/calculate/kelly")
def calculate_kelly(req: KellyRequest):
    dec    = american_to_decimal(req.american_odds)
    result = kelly_criterion(req.fair_prob, dec, kelly_fraction=0.5)
    return {
        "fair_prob":          req.fair_prob,
        "american_odds":      req.american_odds,
        "decimal_odds":       result.decimal_odds,
        "edge":               result.edge,
        "half_kelly_pct":     result.half_kelly * 100,
        "half_kelly_dollars": round(req.bankroll * result.half_kelly, 2),
        "rationale":          result.rationale,
    }


@app.post("/calculate/parlay")
def calculate_parlay(req: ParlayRequest):
    result = parlay_odds(req.legs, fmt="american")
    return {
        "legs":          req.legs,
        "decimal_odds":  result["decimal_odds"],
        "american_odds": result["american_odds"],
        "implied_pct":   result["implied_prob_pct"],
    }


@app.post("/calculate/bankroll")
def calculate_bankroll(req: BankrollRequest):
    return bankroll_summary(req.bankroll, num_bets_day=req.bets_today)