// src/api/betiqClient.ts
// Typed client for the BetIQ FastAPI backend.
// Uses VITE_API_URL env var so the same code works locally and on Vercel.

import type {
  ChatMessage,
  ChatResponse,
  OddsResponse,
  EVResponse,
  KellyResponse,
  ParlayResponse,
  BankrollResponse,
  Sport,
  Market,
} from "../types/betiq";

// ── Base URL ──────────────────────────────────────────────────────────────────
// In development:  set VITE_API_URL=http://localhost:8000 in frontend/.env.local
// In production:   set VITE_API_URL=https://your-api.onrender.com in Vercel dashboard

const BASE_URL = (import.meta.env.VITE_API_URL as string) ?? "http://localhost:8000";

// ── Internal fetch wrapper ────────────────────────────────────────────────────

async function req<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }

  return res.json() as Promise<T>;
}

// ── API client ────────────────────────────────────────────────────────────────

export const betiqClient = {

  /** Health check — call on mount to verify the backend is reachable */
  health: () => req<{ status: string }>("/health"),

  /** Fetch live odds for a sport */
  getOdds: (sport: Sport, market: Market = "h2h", maxGames = 10) =>
    req<OddsResponse>(
      `/odds/${sport}?market=${market}&max_games=${maxGames}`
    ),

  /** Single-turn chat (non-streaming) */
  chat: (
    message: string,
    history: ChatMessage[] = [],
    sport?: Sport,
    market: Market = "h2h"
  ) =>
    req<ChatResponse>("/chat", {
      method: "POST",
      body: JSON.stringify({ message, history, sport, market }),
    }),

  /**
   * Streaming chat via Server-Sent Events.
   *
   * Usage:
   *   const close = betiqClient.chatStream(
   *     "hello", history, "nba",
   *     (chunk) => setReply(r => r + chunk),
   *     () => setLoading(false)
   *   );
   *   // call close() to abort
   */
  chatStream: (
    message: string,
    history: ChatMessage[],
    sport: Sport | undefined,
    onChunk: (chunk: string) => void,
    onDone: () => void,
    onError?: (err: Error) => void
  ): (() => void) => {
    const controller = new AbortController();

    fetch(`${BASE_URL}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, history, sport }),
      signal: controller.signal,
    })
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        if (!res.body) throw new Error("No response body");

        const reader  = res.body.getReader();
        const decoder = new TextDecoder();
        let   buffer  = "";

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";   // keep incomplete last line

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const payload = line.slice(6).trim();
            if (payload === "[DONE]") { onDone(); return; }
            try {
              const parsed = JSON.parse(payload) as { chunk: string };
              onChunk(parsed.chunk);
            } catch {
              // skip malformed chunk
            }
          }
        }
        onDone();
      })
      .catch((err: Error) => {
        if (err.name === "AbortError") return;   // user cancelled — not an error
        onError?.(err);
      });

    return () => controller.abort();
  },

  /** AI deep analysis of a sport/team */
  analyze: (sport: Sport, teamFilter?: string, market: Market = "h2h") => {
    const params = new URLSearchParams({ market });
    if (teamFilter) params.set("team_filter", teamFilter);
    return req<{ analysis: string; events_analyzed: number }>(
      `/analyze/${sport}?${params}`
    );
  },

  /** Expected value calculation */
  calculateEV: (fairProb: number, americanOdds: number, stake = 100) =>
    req<EVResponse>("/calculate/ev", {
      method: "POST",
      body: JSON.stringify({
        fair_prob: fairProb,
        american_odds: americanOdds,
        stake,
      }),
    }),

  /** Kelly Criterion sizing */
  calculateKelly: (fairProb: number, americanOdds: number, bankroll = 1000) =>
    req<KellyResponse>("/calculate/kelly", {
      method: "POST",
      body: JSON.stringify({
        fair_prob: fairProb,
        american_odds: americanOdds,
        bankroll,
      }),
    }),

  /** Parlay combined odds */
  calculateParlay: (legs: number[]) =>
    req<ParlayResponse>("/calculate/parlay", {
      method: "POST",
      body: JSON.stringify({ legs }),
    }),

  /** Bankroll management summary */
  calculateBankroll: (bankroll: number, betsToday = 3) =>
    req<BankrollResponse>("/calculate/bankroll", {
      method: "POST",
      body: JSON.stringify({ bankroll, bets_today: betsToday }),
    }),
};