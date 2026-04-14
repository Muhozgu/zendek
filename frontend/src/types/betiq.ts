// src/types/betiq.ts
// All types that mirror the FastAPI response shapes.

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
}

export interface ChatResponse {
  reply: string;
  history: ChatMessage[];
}

export interface Outcome {
  name: string;
  odds: number;
  decimal: number;
  implied_prob: number;
  point?: number;
}

export interface BookmakerLine {
  bookmaker: string;
  outcomes: Outcome[];
  overround: number;
  vig_pct: number;
}

export interface BestOdds {
  [outcomeName: string]: {
    best_odds: number;
    book: string;
    decimal: number;
    implied_prob: number;
  };
}

export interface ArbSide {
  outcome: string;
  odds: number;
  book: string;
  stake_pct: number;
}

export interface ArbResult {
  arb_exists: boolean;
  profit_pct: number;
  total_implied_prob: number;
  sides: ArbSide[];
}

export interface GameOdds {
  event_id: string;
  sport: string;
  home_team: string;
  away_team: string;
  commence_time: string;
  market: string;
  bookmakers: BookmakerLine[];
  best_odds: BestOdds;
  arbitrage: ArbResult | null;
}

export interface OddsResponse {
  sport: string;
  market: string;
  event_count: number;
  events: GameOdds[];
  quota: string;
}

export interface EVResponse {
  fair_prob: number;
  american_odds: number;
  decimal_odds: number;
  market_implied_prob: number;
  stake: number;
  expected_value: number;
  payout_if_win: number;
  is_value_bet: boolean;
  break_even_prob: number;
}

export interface KellyResponse {
  fair_prob: number;
  american_odds: number;
  decimal_odds: number;
  edge: number;
  half_kelly_pct: number;
  half_kelly_dollars: number;
  rationale: string;
}

export interface ParlayResponse {
  legs: number[];
  decimal_odds: number;
  american_odds: number;
  implied_pct: number;
}

export interface BankrollResponse {
  bankroll: number;
  flat_bet_5pct: number;
  kelly_bet: number;
  daily_exposure: number;
  daily_risk_pct: number;
  warnings: string[];
  recommendation: string;
}

export type Sport =
  | "nba" | "nfl" | "nhl" | "mlb"
  | "epl" | "la_liga" | "ucl" | "mls"
  | "ncaaf" | "tennis" | "ufc";

export type Market = "h2h" | "spreads" | "totals";