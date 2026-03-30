"""
gradio_app.py
-------------
BetIQ — Web UI powered by Gradio.

Run:  python gradio_app.py
Open: http://localhost:7860

Tabs
----
1. Chat       — multi-turn AI chat with optional live odds context
2. Live Odds  — fetch & display a formatted odds table
3. Analyze    — AI deep-dive on a specific game or whole league
4. Calculator — Kelly / EV / Parlay / Bankroll tools
"""

from __future__ import annotations

import os
import json
from typing import Optional



import gradio as gr
from dotenv import load_dotenv

from clients.odds_api_client import OddsAPIClient, OddsAPIError, SPORT_KEYS
from clients.groq_client import GroqChatClient
from tools.odds_tools import OddsAnalyzer, parse_events
from tools.betting_tools import (
    BettingCalculator,
    RESPONSIBLE_GAMBLING_REMINDER,
    american_to_decimal,
    american_to_implied_prob,
    parlay_odds,
)

load_dotenv()

# ── Singletons ────────────────────────────────────────────────────────────────
_odds  = OddsAPIClient()
_groq  = GroqChatClient()
_calc  = BettingCalculator()

SPORT_CHOICES = list(SPORT_KEYS.keys())


# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — Chat
# ─────────────────────────────────────────────────────────────────────────────

def chat_response(
    message: str,
    history: list,          # Gradio passes [[user, bot], ...]
    sport_ctx: str,
    market_ctx: str,
) -> tuple[str, list]:
    """Stream a reply and update chat history."""
    if not message.strip():
        return "", history

    # Build Groq-format history from Gradio format
    groq_history = []
    for user_msg, bot_msg in history:
        groq_history.append({"role": "user",      "content": user_msg})
        groq_history.append({"role": "assistant", "content": bot_msg})

    # Optionally inject live odds context
    context: Optional[str] = None
    if sport_ctx and sport_ctx != "None":
        try:
            raw    = _odds.get_odds(sport_ctx, markets=market_ctx)
            events = parse_events(raw)
            context = OddsAnalyzer.format_for_llm(events, market_ctx)
        except OddsAPIError as e:
            context = f"[Could not load odds: {e}]"

    # Accumulate full reply for history
    full_reply = ""
    for chunk in _groq.stream(message, history=groq_history, context=context):
        full_reply += chunk

    history = history + [[message, full_reply]]
    return "", history


def clear_chat() -> tuple[list, str]:
    return [], ""


# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — Live Odds
# ─────────────────────────────────────────────────────────────────────────────

def fetch_odds(sport: str, market: str, max_games: int) -> tuple[str, str]:
    """
    Returns (markdown_table, quota_info_string).
    """
    try:
        raw    = _odds.get_odds(sport, markets=market)
        events = parse_events(raw)
    except OddsAPIError as e:
        return f"**API Error:** {e}", ""
    except ValueError as e:
        return f"**Invalid sport:** {e}", ""

    if not events:
        return f"No upcoming {sport.upper()} events found.", ""

    lines = [f"## {sport.upper()} — {market.upper()} Odds  ({len(events)} events)\n"]

    for ev in events[:max_games]:
        lines.append(f"### {ev.away_team} @ {ev.home_team}")
        lines.append(f"*{ev.commence_time[:16].replace('T', ' ')} UTC*\n")

        comparison = OddsAnalyzer.odds_comparison_table(ev, market)
        if not comparison:
            lines.append("*No odds data*\n")
            continue

        # Markdown table header
        outcome_names = [o["name"] for o in comparison[0]["outcomes"]]
        header = "| Bookmaker | " + " | ".join(outcome_names) + " | Vig % |"
        sep    = "|---|" + "|".join(["---"] * len(outcome_names)) + "|---|"
        lines += [header, sep]

        # Find best odds per outcome
        best = OddsAnalyzer.best_available_odds(ev, market)

        for row in comparison:
            cells = [row["bookmaker"]]
            for o in row["outcomes"]:
                is_best  = (o["name"] in best and
                            abs(o["decimal"] - best[o["name"]]["decimal"]) < 0.001)
                odds_str = f"{o['odds']:+.0f} ({o['implied_prob']:.1f}%)"
                cells.append(f"**{odds_str}**" if is_best else odds_str)
            cells.append(f"{row['vig_pct']:.2f}%")
            lines.append("| " + " | ".join(cells) + " |")

        lines.append("")

        # Best available
        lines.append("**Best available:**")
        for name, info in best.items():
            lines.append(f"- {name}: `{info['best_odds']:+.0f}` @ {info['book']} "
                         f"({info['implied_prob']*100:.1f}% implied)")

        # Arb check
        arb = OddsAnalyzer.detect_arbitrage(ev, market)
        if arb:
            lines.append(f"\n⚡ **ARBITRAGE DETECTED — {arb['profit_pct']:.2f}% guaranteed profit**")
            for side in arb["sides"]:
                lines.append(f"  → {side['outcome']} `{side['odds']:+.0f}` @ {side['book']} "
                             f"(stake {side['stake_pct']:.1f}%)")

        lines.append("\n---")

    quota = _odds.quota_status()
    return "\n".join(lines), f"📊 {quota}"


# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — AI Analysis
# ─────────────────────────────────────────────────────────────────────────────

def run_analysis(sport: str, team_filter: str, market: str) -> str:
    try:
        raw    = _odds.get_odds(sport, markets=market)
        events = parse_events(raw)
    except OddsAPIError as e:
        return f"**API Error:** {e}"

    if team_filter.strip():
        tf = team_filter.strip().lower()
        events = [e for e in events
                  if tf in e.home_team.lower() or tf in e.away_team.lower()]

    if not events:
        return "No matching events found."

    context = OddsAnalyzer.format_for_llm(events, market)
    prompt  = (
        f"Analyze {'this game' if len(events)==1 else f'these {len(events)} upcoming games'}. "
        "For each: (1) identify implied probabilities, (2) calculate the vig, "
        "(3) flag line discrepancies across bookmakers, (4) highlight best available odds, "
        "(5) flag any potential value or arbitrage. Be specific with numbers."
    )

    result = _groq.chat(prompt, context=context)
    return result + "\n\n---\n" + RESPONSIBLE_GAMBLING_REMINDER


# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 — Calculators
# ─────────────────────────────────────────────────────────────────────────────

def calc_ev(fair_prob: float, american_odds: float, stake: float) -> str:
    try:
        result = _calc.ev(fair_prob, american_odds, stake)
    except Exception as e:
        return f"Error: {e}"

    sign   = "+" if result["expected_value"] >= 0 else ""
    verdict = "✅ VALUE BET" if result["expected_value"] >= 0 else "❌ NO VALUE"

    kelly  = _calc.kelly(fair_prob, american_odds)

    return f"""## Expected Value Analysis

| Metric | Value |
|---|---|
| Offered Odds (American) | `{american_odds:+.0f}` |
| Offered Odds (Decimal) | `{result['decimal_odds']:.4f}` |
| Break-even Probability | `{result['break_even_prob']:.2f}%` |
| Your Fair Probability | `{fair_prob*100:.2f}%` |
| Stake | `${stake:.2f}` |
| Payout if Win | `${result['payout_if_win']:.2f}` |
| **Expected Value** | **`{sign}${result['expected_value']:.2f}`** |
| Verdict | **{verdict}** |

## Kelly Criterion (Half-Kelly recommended)

| | |
|---|---|
| Edge | `{kelly.edge*100:.2f}%` |
| Half-Kelly fraction | `{kelly.half_kelly*100:.2f}% of bankroll` |
| Quarter-Kelly fraction | `{kelly.quarter_kelly*100:.2f}% of bankroll` |
| Rationale | {kelly.rationale} |

> ⚠️ Past edge does not guarantee future results. Bet responsibly.
"""


def calc_kelly(fair_prob: float, american_odds: float, bankroll: float) -> str:
    try:
        result = _calc.kelly(fair_prob, american_odds)
    except Exception as e:
        return f"Error: {e}"

    return f"""## Kelly Criterion Calculator

| Metric | Value |
|---|---|
| Fair Probability | `{fair_prob*100:.2f}%` |
| Offered Odds | `{american_odds:+.0f}` (American) |
| Decimal Odds | `{result.decimal_odds:.4f}` |
| Estimated Edge | `{result.edge*100:.2f}%` |
| Full Kelly % | `{result.fraction_pct:.2f}%` |
| **Half Kelly % (recommended)** | **`{result.half_kelly*100:.2f}%`** |
| Quarter Kelly % | `{result.quarter_kelly*100:.2f}%` |
| **Half Kelly $ on ${bankroll:.0f} bankroll** | **`${bankroll * result.half_kelly:.2f}`** |
| Quarter Kelly $ | `${bankroll * result.quarter_kelly:.2f}` |

**Rationale:** {result.rationale}
"""


def calc_parlay(legs_input: str) -> str:
    """Parse space or comma-separated American odds."""
    try:
        raw_legs = legs_input.replace(",", " ").split()
        legs     = [float(x) for x in raw_legs if x]
        if len(legs) < 2:
            return "Please enter at least 2 odds separated by spaces."
        result = parlay_odds(legs, fmt="american")
    except ValueError:
        return "Invalid input. Enter American odds separated by spaces, e.g.: -110 -115 +130"

    rows = "\n".join(
        f"| {i+1} | `{leg:+.0f}` | `{american_to_decimal(leg):.4f}` | "
        f"`{american_to_implied_prob(leg)*100:.2f}%` |"
        for i, leg in enumerate(legs)
    )

    return f"""## {len(legs)}-Leg Parlay Calculator

| Leg | American | Decimal | Implied Prob |
|---|---|---|---|
{rows}

## Combined Result

| | |
|---|---|
| **Combined American Odds** | **`{result['american_odds']:+.0f}`** |
| Combined Decimal Odds | `{result['decimal_odds']:.4f}` |
| Implied Win Probability | `{result['implied_prob_pct']:.2f}%` |

> ⚠️ Parlays compound the vig from every leg. They have significantly lower EV than single bets.
"""


def calc_bankroll(bankroll: float, bets_today: int) -> str:
    result = _calc.bankroll(bankroll, bets_today=bets_today)
    warnings = "\n".join(f"- {w}" for w in result["warnings"]) or "- No major warnings."

    return f"""## Bankroll Management Summary

| Metric | Value |
|---|---|
| Total Bankroll | `${result['bankroll']:.2f}` |
| Max Single Bet (5%) | `${result['flat_bet_5pct']:.2f}` |
| Planned Bets Today | `{bets_today}` |
| Max Daily Exposure | `${result['daily_exposure']:.2f}` |
| Daily Risk % | `{result['daily_risk_pct']:.1f}%` |

## Warnings
{warnings}

## Recommendation
{result['recommendation']}

{RESPONSIBLE_GAMBLING_REMINDER}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Gradio UI
# ─────────────────────────────────────────────────────────────────────────────

THEME = gr.themes.Base(
    primary_hue="emerald",
    secondary_hue="slate",
    neutral_hue="slate",
    font=[gr.themes.GoogleFont("DM Mono"), "monospace"],
).set(
    body_background_fill="#0f1117",
    body_text_color="#e2e8f0",
    block_background_fill="#1a1f2e",
    block_border_color="#2d3748",
    input_background_fill="#0f1117",
    button_primary_background_fill="#10b981",
    button_primary_text_color="#000",
)

with gr.Blocks(
    theme=THEME,
    title="BetIQ — Sports Betting AI",
    css="""
    .gradio-container { max-width: 1100px !important; }
    .betiq-header { text-align: center; padding: 1.5rem 0 0.5rem; }
    .betiq-header h1 { font-size: 2rem; color: #10b981; letter-spacing: 0.05em; }
    .betiq-header p  { color: #64748b; font-size: 0.9rem; }
    footer { display: none !important; }
    """,
) as demo:

    gr.HTML("""
    <div class="betiq-header">
      <h1>⚡ BetIQ</h1>
      <p>Sports Betting AI · Groq Llama 3 · The Odds API</p>
    </div>
    """)

    with gr.Tabs():

        # ── Tab 1: Chat ───────────────────────────────────────────────────────
        with gr.Tab("🤖 AI Chat"):
            with gr.Row():
                sport_ctx  = gr.Dropdown(
                    choices=["None"] + SPORT_CHOICES,
                    value="None",
                    label="Pre-load live odds for sport",
                    scale=2,
                )
                market_ctx = gr.Dropdown(
                    choices=["h2h", "spreads", "totals"],
                    value="h2h",
                    label="Market",
                    scale=1,
                )

            chatbot = gr.Chatbot(
                label="BetIQ Chat",
                height=480,
                show_copy_button=True,
                bubble_full_width=False,
            )

            with gr.Row():
                msg_box = gr.Textbox(
                    placeholder="Ask anything: 'Analyze tonight's NBA games', "
                                "'What's the implied prob for -120?', 'Best line for the Lakers?'",
                    label="Your message",
                    scale=5,
                    lines=1,
                )
                send_btn  = gr.Button("Send ↵", variant="primary", scale=1)
                clear_btn = gr.Button("Clear", scale=1)

            gr.Examples(
                examples=[
                    ["What are tonight's best value bets?"],
                    ["Explain the Kelly Criterion to me"],
                    ["What's the implied probability of -115 odds?"],
                    ["Is there any arbitrage in tonight's games?"],
                    ["How should I manage a $500 bankroll?"],
                ],
                inputs=msg_box,
            )

            send_btn.click(
                chat_response,
                inputs=[msg_box, chatbot, sport_ctx, market_ctx],
                outputs=[msg_box, chatbot],
            )
            msg_box.submit(
                chat_response,
                inputs=[msg_box, chatbot, sport_ctx, market_ctx],
                outputs=[msg_box, chatbot],
            )
            clear_btn.click(lambda: ([], ""), outputs=[chatbot, msg_box])

        # ── Tab 2: Live Odds ──────────────────────────────────────────────────
        with gr.Tab("📊 Live Odds"):
            with gr.Row():
                odds_sport  = gr.Dropdown(SPORT_CHOICES, value="nba", label="Sport", scale=2)
                odds_market = gr.Dropdown(["h2h", "spreads", "totals"], value="h2h",
                                          label="Market", scale=1)
                odds_max    = gr.Slider(1, 10, value=5, step=1, label="Max games", scale=1)
                odds_btn    = gr.Button("Fetch Odds 🔄", variant="primary", scale=1)

            odds_quota  = gr.Textbox(label="API Quota", interactive=False, lines=1)
            odds_output = gr.Markdown(label="Odds Table")

            odds_btn.click(
                fetch_odds,
                inputs=[odds_sport, odds_market, odds_max],
                outputs=[odds_output, odds_quota],
            )

        # ── Tab 3: Analyze ────────────────────────────────────────────────────
        with gr.Tab("🔍 AI Analysis"):
            with gr.Row():
                an_sport  = gr.Dropdown(SPORT_CHOICES, value="nba", label="Sport", scale=2)
                an_team   = gr.Textbox(placeholder="e.g. Lakers (leave blank for all)",
                                       label="Team filter (optional)", scale=2)
                an_market = gr.Dropdown(["h2h", "spreads", "totals"], value="h2h",
                                        label="Market", scale=1)
                an_btn    = gr.Button("Analyze 🧠", variant="primary", scale=1)

            an_output = gr.Markdown(label="AI Analysis")

            an_btn.click(
                run_analysis,
                inputs=[an_sport, an_team, an_market],
                outputs=an_output,
            )

        # ── Tab 4: Calculators ────────────────────────────────────────────────
        with gr.Tab("🧮 Calculators"):
            with gr.Tabs():

                with gr.Tab("Expected Value"):
                    with gr.Row():
                        ev_prob  = gr.Slider(0.01, 0.99, value=0.55, step=0.01,
                                             label="Your fair probability")
                        ev_odds  = gr.Number(value=-110, label="Offered odds (American)")
                        ev_stake = gr.Number(value=100,  label="Stake ($)")
                    ev_btn = gr.Button("Calculate EV", variant="primary")
                    ev_out = gr.Markdown()
                    ev_btn.click(calc_ev, inputs=[ev_prob, ev_odds, ev_stake], outputs=ev_out)

                with gr.Tab("Kelly Criterion"):
                    with gr.Row():
                        kl_prob  = gr.Slider(0.01, 0.99, value=0.55, step=0.01,
                                             label="Your fair probability")
                        kl_odds  = gr.Number(value=-110, label="Offered odds (American)")
                        kl_broll = gr.Number(value=1000, label="Bankroll ($)")
                    kl_btn = gr.Button("Calculate Kelly", variant="primary")
                    kl_out = gr.Markdown()
                    kl_btn.click(calc_kelly, inputs=[kl_prob, kl_odds, kl_broll], outputs=kl_out)

                with gr.Tab("Parlay Calculator"):
                    parlay_input = gr.Textbox(
                        value="-110 -115 +130",
                        label="Leg odds (space or comma separated, American format)",
                        placeholder="-110 -115 +130",
                    )
                    parlay_btn = gr.Button("Calculate Parlay", variant="primary")
                    parlay_out = gr.Markdown()
                    parlay_btn.click(calc_parlay, inputs=parlay_input, outputs=parlay_out)

                with gr.Tab("Bankroll Manager"):
                    with gr.Row():
                        bm_amount = gr.Number(value=1000, label="Your bankroll ($)")
                        bm_bets   = gr.Slider(1, 10, value=3, step=1, label="Bets planned today")
                    bm_btn = gr.Button("Generate Summary", variant="primary")
                    bm_out = gr.Markdown()
                    bm_btn.click(calc_bankroll, inputs=[bm_amount, bm_bets], outputs=bm_out)

    gr.HTML("""
    <div style="text-align:center; padding: 1rem; color: #475569; font-size:0.8rem;">
      ⚠️ For educational & analytical purposes only. Bet responsibly.
      · <a href="https://www.ncpgambling.org" style="color:#10b981">ncpgambling.org</a>
      · Helpline: 1-800-522-4700
    </div>
    """)


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,           # set True to get a public Gradio link
        show_error=True,
    )