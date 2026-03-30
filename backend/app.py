"""
app.py
------
Zendek — Sports Betting AI Chatbot (CLI)

Commands
--------
  chat      Interactive multi-turn chat with the AI (supports live odds injection)
  odds      Fetch and display live odds for a sport/league
  analyze   Deep AI analysis of a specific game
  value     Calculate value bets given your own probability estimate
  kelly     Kelly Criterion bet sizing calculator
  parlay    Parlay odds calculator
  bankroll  Bankroll management summary
  sports    List all supported sports and leagues

Run `python app.py --help` for usage, or `python app.py <command> --help`.
"""

from __future__ import annotations

import os
import sys
import json
import logging
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.markdown import Markdown
from rich.prompt import Prompt
from rich.live import Live
from rich.spinner import Spinner
from rich.rule import Rule
from dotenv import load_dotenv

from clients.odds_api_client import OddsAPIClient, OddsAPIError, SPORT_KEYS
from clients.groq_client import GroqChatClient
from tools.odds_tools import OddsAnalyzer, parse_events
from tools.betting_tools import BettingCalculator, RESPONSIBLE_GAMBLING_REMINDER

load_dotenv()

# ──────────────────────────────────────────────────────────────────────────────
# Setup
# ──────────────────────────────────────────────────────────────────────────────

DEBUG = os.getenv("DEBUG", "false").lower() == "true"
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.WARNING,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)

app     = typer.Typer(help="Zendek — Sports Betting AI powered by Groq Llama + The Odds API")
console = Console()


# ──────────────────────────────────────────────────────────────────────────────
# Lazy-initialised singletons
# ──────────────────────────────────────────────────────────────────────────────

_odds_client: Optional[OddsAPIClient] = None
_groq_client: Optional[GroqChatClient] = None


def get_odds_client() -> OddsAPIClient:
    global _odds_client
    if _odds_client is None:
        _odds_client = OddsAPIClient()
    return _odds_client


def get_groq_client() -> GroqChatClient:
    global _groq_client
    if _groq_client is None:
        _groq_client = GroqChatClient()
    return _groq_client


# ──────────────────────────────────────────────────────────────────────────────
# Display helpers
# ──────────────────────────────────────────────────────────────────────────────

def print_header() -> None:
    console.print()
    console.print(Panel(
        "[bold green]Zendek[/] — Sports Betting AI Analyst\n"
        "[dim]Powered by Groq Llama 3 + The Odds API[/]",
        border_style="green",
        padding=(0, 2),
    ))
    console.print()


def print_responsible_reminder() -> None:
    console.print(Panel(
        RESPONSIBLE_GAMBLING_REMINDER,
        border_style="yellow",
        title="⚠️  Responsible Gambling",
    ))


def spinner_context(message: str):
    """Context manager that shows a spinner while work is happening."""
    return console.status(f"[dim]{message}[/]", spinner="dots")


def display_odds_table(comparison_rows: list[dict], event_label: str) -> None:
    """Render a Rich table of bookmaker odds for one event."""
    if not comparison_rows:
        console.print("[yellow]No odds data available.[/]")
        return

    # Determine columns from first row
    outcome_names = [o["name"] for o in comparison_rows[0]["outcomes"]]

    table = Table(title=event_label, show_header=True, header_style="bold cyan")
    table.add_column("Bookmaker", style="bold", min_width=14)
    for name in outcome_names:
        table.add_column(name, justify="center", min_width=18)
    table.add_column("Vig %", justify="right", style="dim", min_width=7)

    # Highlight the best odds per outcome column
    best_dec = {}
    for row in comparison_rows:
        for o in row["outcomes"]:
            if o["name"] not in best_dec or o["decimal"] > best_dec[o["name"]]:
                best_dec[o["name"]] = o["decimal"]

    for row in comparison_rows:
        cells = [row["bookmaker"]]
        for o in row["outcomes"]:
            odds_str = f"{o['odds']:+.0f}"
            prob_str = f"({o['implied_prob']:.1f}%)"
            is_best  = abs(o["decimal"] - best_dec.get(o["name"], 0)) < 0.0001
            color    = "bold green" if is_best else "white"
            cells.append(f"[{color}]{odds_str}[/]\n[dim]{prob_str}[/]")
        cells.append(f"{row['vig_pct']:.2f}%")
        table.add_row(*cells)

    console.print(table)


# ──────────────────────────────────────────────────────────────────────────────
# Commands
# ──────────────────────────────────────────────────────────────────────────────

@app.command()
def chat(
    sport: str = typer.Option(
        None, "--sport", "-s",
        help="Pre-load odds for a sport into the conversation (e.g. nba, nfl, epl)"
    ),
    market: str = typer.Option("h2h", "--market", "-m", help="Market type: h2h | spreads | totals"),
    no_stream: bool = typer.Option(False, "--no-stream", help="Disable streaming output"),
) -> None:
    """
    🤖  Interactive chat with the Zendek.

    Optionally pre-loads live odds for a sport so the AI can answer
    specific questions about today's games.

    Examples
    --------
    python app.py chat
    python app.py chat --sport nba
    python app.py chat --sport epl --market h2h
    """
    print_header()

    # Optionally fetch live context
    live_context: Optional[str] = None
    if sport:
        with spinner_context(f"Fetching live {sport.upper()} odds …"):
            try:
                client  = get_odds_client()
                raw     = client.get_odds(sport, markets=market)
                events  = parse_events(raw)
                live_context = OddsAnalyzer.format_for_llm(events, market)
                console.print(f"[green]✓[/] Loaded {len(events)} {sport.upper()} events into context.\n")
            except OddsAPIError as e:
                console.print(f"[yellow]⚠ Could not load odds: {e}[/]\n")

    groq  = get_groq_client()
    history: list[dict] = []

    console.print("[dim]Type [bold]exit[/bold] or [bold]quit[/bold] to end the session.[/]")
    console.print("[dim]Type [bold]odds[/bold] to reload live data mid-session.[/]")
    console.print("[dim]Type [bold]reminder[/bold] to show the responsible gambling reminder.[/]\n")

    while True:
        try:
            user_input = Prompt.ask("[bold cyan]You[/]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Session ended.[/]")
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit", "q"):
            console.print("[dim]Goodbye — bet responsibly! 🍀[/]")
            break

        if user_input.lower() == "reminder":
            print_responsible_reminder()
            continue

        # --- stream or single-shot ---
        console.print()
        console.print("[bold green]Zendek[/] ", end="")

        full_reply = ""
        if no_stream:
            with spinner_context("Thinking …"):
                reply, history = groq.chat_with_history(user_input, history, live_context)
            console.print(Markdown(reply))
            full_reply = reply
        else:
            gen, history = groq.stream_with_history(user_input, history, live_context)
            for chunk in gen:
                console.print(chunk, end="", markup=False)
                full_reply += chunk
            console.print()

            # Update the placeholder in history with the actual reply
            if history and history[-1]["role"] == "assistant":
                history[-1]["content"] = full_reply

        console.print()

        # After every real-bet-related answer, append a brief reminder
        if any(kw in user_input.lower() for kw in ("bet", "stake", "wager", "place", "kelly")):
            console.print(
                "[dim yellow]⚠  Remember: sports betting involves real financial risk. "
                "Never bet more than you can afford to lose.[/dim yellow]\n"
            )


@app.command()
def odds(
    sport: str = typer.Argument(..., help="Sport alias: nba | nfl | epl | mlb | nhl | mls | ucl …"),
    market: str = typer.Option("h2h", "--market", "-m", help="h2h | spreads | totals"),
    max_games: int = typer.Option(5, "--max", "-n", help="Maximum number of games to show"),
    export: Optional[str] = typer.Option(None, "--export", "-e", help="Export raw JSON to file path"),
) -> None:
    """
    📊  Fetch and display live odds for a sport/league.

    Examples
    --------
    python app.py odds nba
    python app.py odds epl --market h2h
    python app.py odds nfl --market spreads --max 3
    python app.py odds nba --export nba_odds.json
    """
    with spinner_context(f"Fetching {sport.upper()} odds ({market}) …"):
        try:
            client = get_odds_client()
            raw    = client.get_odds(sport, markets=market)
        except OddsAPIError as e:
            console.print(f"[red]API Error:[/] {e}")
            raise typer.Exit(1)
        except ValueError as e:
            console.print(f"[red]Invalid input:[/] {e}")
            raise typer.Exit(1)

    if not raw:
        console.print(f"[yellow]No upcoming {sport.upper()} events found.[/]")
        raise typer.Exit(0)

    events = parse_events(raw)

    console.print(f"\n[bold]{sport.upper()} — {market.upper()} Odds[/]  "
                  f"([dim]{len(events)} events[/])\n")

    for ev in events[:max_games]:
        label = f"{ev.away_team} @ {ev.home_team}  [{ev.commence_time[:10]}]"
        comparison = OddsAnalyzer.odds_comparison_table(ev, market)
        display_odds_table(comparison, label)

        # Arbitrage check
        arb = OddsAnalyzer.detect_arbitrage(ev, market)
        if arb:
            console.print(
                f"  [bold green]⚡ ARB DETECTED[/] — guaranteed profit: "
                f"[green]{arb['profit_pct']:.2f}%[/]"
            )
            for side in arb["sides"]:
                console.print(
                    f"    → {side['outcome']} @ {side['odds']:+.0f} via {side['book']} "
                    f"(stake {side['stake_pct']:.1f}%)"
                )
        console.print()

    # Show quota info
    console.print(f"[dim]{client.quota_status()}[/]\n")

    if export:
        with open(export, "w") as f:
            json.dump(raw, f, indent=2)
        console.print(f"[green]✓[/] Raw odds exported to [bold]{export}[/]")


@app.command()
def analyze(
    sport: str = typer.Argument(..., help="Sport alias: nba | nfl | epl …"),
    game: Optional[str] = typer.Option(None, "--game", "-g", help="Team name to filter (partial match)"),
    market: str = typer.Option("h2h", "--market", "-m", help="Market type: h2h | spreads | totals"),
) -> None:
    """
    🔍  Deep AI analysis of a specific game or all games for a sport.

    Examples
    --------
    python app.py analyze nba
    python app.py analyze nba --game "Lakers"
    python app.py analyze epl --game "Arsenal"
    """
    print_header()

    with spinner_context(f"Fetching {sport.upper()} data …"):
        try:
            client = get_odds_client()
            raw    = client.get_odds(sport, markets=market)
        except OddsAPIError as e:
            console.print(f"[red]API Error:[/] {e}")
            raise typer.Exit(1)

    events = parse_events(raw)

    if game:
        events = [
            ev for ev in events
            if game.lower() in ev.home_team.lower()
            or game.lower() in ev.away_team.lower()
        ]

    if not events:
        console.print(f"[yellow]No matching events found.[/]")
        raise typer.Exit(0)

    context = OddsAnalyzer.format_for_llm(events, market)

    query = (
        f"Please analyze the {'following game' if len(events) == 1 else f'{len(events)} upcoming games'}. "
        f"For each game: (1) identify the implied probabilities, (2) calculate the vig, "
        f"(3) flag any line discrepancies across bookmakers, (4) highlight the best available odds, "
        f"(5) note any potential value. Be specific with numbers."
    )

    console.print(f"\n[bold]AI Analysis — {sport.upper()}[/]\n")
    groq = get_groq_client()

    console.print("[bold green]Zendek[/] ", end="")
    for chunk in groq.stream(query, context=context):
        console.print(chunk, end="", markup=False)
    console.print("\n")

    print_responsible_reminder()


@app.command()
def value(
    odds_american: float = typer.Argument(..., help="The offered odds in American format (e.g. -110, +150)"),
    fair_prob: float = typer.Argument(..., help="Your estimated probability of winning (0.0–1.0)"),
    stake: float = typer.Option(100.0, "--stake", "-s", help="Bet stake in dollars"),
) -> None:
    """
    💡  Calculate expected value and Kelly sizing for a specific bet.

    Examples
    --------
    python app.py value -- -110 0.55
    python app.py value 150 0.40 --stake 200
    """
    if not 0.0 < fair_prob < 1.0:
        console.print("[red]Error:[/] fair_prob must be between 0.0 and 1.0")
        raise typer.Exit(1)

    calc = BettingCalculator()
    ev   = calc.ev(fair_prob, odds_american, stake)
    kelly = calc.kelly(fair_prob, odds_american)

    console.print()
    console.print(Rule("[bold]Value Bet Analysis[/]"))
    console.print()

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Metric", style="dim")
    table.add_column("Value", style="bold")

    sign = "+" if ev["expected_value"] >= 0 else ""
    ev_color = "green" if ev["expected_value"] >= 0 else "red"
    value_label = "[green]✓ VALUE BET[/]" if ev["expected_value"] >= 0 else "[red]✗ NO VALUE[/]"

    table.add_row("Offered Odds (American)", f"{odds_american:+.0f}")
    table.add_row("Offered Odds (Decimal)", f"{ev['decimal_odds']:.4f}")
    table.add_row("Market Implied Prob", f"{ev['break_even_prob']:.2f}%")
    table.add_row("Your Fair Prob", f"{fair_prob*100:.2f}%")
    table.add_row("Stake", f"${stake:.2f}")
    table.add_row("Payout if Win", f"${ev['payout_if_win']:.2f}")
    table.add_row(f"Expected Value", f"[{ev_color}]{sign}${ev['expected_value']:.2f}[/]")
    table.add_row("Verdict", value_label)
    table.add_row("", "")
    table.add_row("Kelly Fraction (half)", f"{kelly.half_kelly*100:.2f}% of bankroll")
    table.add_row("Kelly Fraction (quarter)", f"{kelly.quarter_kelly*100:.2f}% of bankroll")
    table.add_row("Estimated Edge", f"{kelly.edge*100:.2f}%")
    table.add_row("Kelly Rationale", kelly.rationale)

    console.print(table)
    console.print()
    console.print("[dim yellow]⚠  Past edge does not guarantee future results. Bet responsibly.[/]")


@app.command()
def kelly(
    fair_prob: float = typer.Argument(..., help="Your win probability (0.0–1.0)"),
    odds_american: float = typer.Argument(..., help="American odds (e.g. -110, +150)"),
    bankroll: float = typer.Option(1000.0, "--bankroll", "-b", help="Your total bankroll in dollars"),
) -> None:
    """
    📐  Kelly Criterion bet sizing calculator.

    Examples
    --------
    python app.py kelly 0.55 -- -110
    python app.py kelly 0.40 150 --bankroll 5000
    """
    if not 0.0 < fair_prob < 1.0:
        console.print("[red]Error:[/] fair_prob must be between 0.0 and 1.0")
        raise typer.Exit(1)

    result = BettingCalculator.kelly(fair_prob, odds_american)

    console.print()
    console.print(Rule("[bold]Kelly Criterion Calculator[/]"))
    console.print()

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("", style="dim")
    table.add_column("", style="bold")

    table.add_row("Fair Probability",    f"{fair_prob*100:.2f}%")
    table.add_row("Offered Odds",        f"{odds_american:+.0f} (American)")
    table.add_row("Decimal Odds",        f"{result.decimal_odds:.4f}")
    table.add_row("Estimated Edge",      f"{result.edge*100:.2f}%")
    table.add_row("", "")
    table.add_row("Full Kelly %",        f"{result.fraction_pct:.2f}% of bankroll")
    table.add_row("Half Kelly % (rec.)", f"[green]{result.half_kelly*100:.2f}% of bankroll[/]")
    table.add_row("Quarter Kelly %",     f"{result.quarter_kelly*100:.2f}% of bankroll")
    table.add_row("", "")
    table.add_row("Half Kelly $ amount", f"[green]${bankroll * result.half_kelly:.2f}[/]")
    table.add_row("Quarter Kelly $",     f"${bankroll * result.quarter_kelly:.2f}")
    table.add_row("", "")
    table.add_row("Rationale",           result.rationale)

    console.print(table)
    console.print()


@app.command()
def parlay(
    legs: list[float] = typer.Argument(..., help="American odds for each leg (e.g. -110 -115 +130)"),
) -> None:
    """
    🎰  Calculate combined parlay odds from individual leg odds.

    Examples
    --------
    python app.py parlay -- -110 -115 +130
    python app.py parlay 150 200 -105
    """
    if len(legs) < 2:
        console.print("[red]Error:[/] A parlay requires at least 2 legs.")
        raise typer.Exit(1)

    result = BettingCalculator.parlay(*legs)

    console.print()
    console.print(Rule(f"[bold]{len(legs)}-Leg Parlay Calculator[/]"))
    console.print()

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Leg", justify="center")
    table.add_column("Odds (American)", justify="center")
    table.add_column("Odds (Decimal)", justify="center")
    table.add_column("Implied Prob", justify="center")

    from tools.betting_tools import american_to_decimal, american_to_implied_prob
    for i, leg in enumerate(legs, 1):
        dec = american_to_decimal(leg)
        imp = american_to_implied_prob(leg)
        table.add_row(
            str(i),
            f"{leg:+.0f}",
            f"{dec:.4f}",
            f"{imp*100:.2f}%",
        )

    console.print(table)
    console.print()

    summary = Table(show_header=False, box=None, padding=(0, 2))
    summary.add_column("", style="dim")
    summary.add_column("", style="bold")
    summary.add_row("Combined Decimal Odds",  f"{result['decimal_odds']:.4f}")
    summary.add_row("Combined American Odds", f"[bold green]{result['american_odds']:+.0f}[/]")
    summary.add_row("Implied Win Probability", f"{result['implied_prob_pct']:.2f}%")
    summary.add_row("Number of Legs",          str(result["num_legs"]))

    console.print(summary)
    console.print()
    console.print(
        "[dim yellow]⚠  Parlays have much lower expected value than single bets "
        "due to compounding vig. Use sparingly.[/dim yellow]"
    )


@app.command()
def bankroll_cmd(
    amount: float = typer.Argument(..., help="Your total bankroll in dollars"),
    bets: int = typer.Option(3, "--bets", "-n", help="Number of bets you plan today"),
) -> None:
    """
    💰  Bankroll management summary and safety check.

    Examples
    --------
    python app.py bankroll 1000
    python app.py bankroll 5000 --bets 5
    """
    result = BettingCalculator.bankroll(amount, bets_today=bets)

    console.print()
    console.print(Rule("[bold]Bankroll Management[/]"))
    console.print()

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("", style="dim")
    table.add_column("", style="bold")

    table.add_row("Total Bankroll",         f"${result['bankroll']:.2f}")
    table.add_row("Max Single Bet (5%)",    f"[cyan]${result['flat_bet_5pct']:.2f}[/]")
    table.add_row("Planned Bets Today",     str(bets))
    table.add_row("Max Daily Exposure",     f"${result['daily_exposure']:.2f}")
    table.add_row("Daily Risk %",           f"{result['daily_risk_pct']:.1f}% of bankroll")

    console.print(table)

    if result["warnings"]:
        console.print()
        for w in result["warnings"]:
            console.print(f"  {w}")

    console.print()
    console.print(Panel(
        result["recommendation"],
        title="Recommendation",
        border_style="cyan",
    ))


# Alias for the command with a friendly name
app.command(name="bankroll")(bankroll_cmd)


@app.command()
def sports() -> None:
    """
    📋  List all supported sports and their API keys.

    Examples
    --------
    python app.py sports
    """
    console.print()
    console.print(Rule("[bold]Supported Sports & Leagues[/]"))
    console.print()

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Alias", style="bold green")
    table.add_column("API Sport Key")
    table.add_column("Use as")

    for alias, key in SPORT_KEYS.items():
        table.add_row(alias, key, f"python app.py odds {alias}")

    console.print(table)
    console.print()
    console.print("[dim]Use the alias (left column) in any command, e.g.:[/]")
    console.print("  python app.py odds nba")
    console.print("  python app.py analyze epl --game Arsenal")
    console.print()


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app()