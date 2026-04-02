"""
clients/groq_client.py
----------------------
Thin, typed wrapper around the Groq SDK.

Supports:
  • Single-turn completions
  • Streaming completions (yields chunks so the CLI can print as tokens arrive)
  • Multi-turn conversation history
  • System prompt injection
  • Automatic retry on transient errors
"""

from __future__ import annotations

import os
import time
import logging
from typing import Generator, Optional

from groq import Groq, APIStatusError, APIConnectionError, RateLimitError
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Default system prompt — shapes the assistant's persona
# ──────────────────────────────────────────────────────────────────────────────

DEFAULT_SYSTEM_PROMPT = """You are an advanced Sports Betting AI Analyst & Advisor.

Your goal is to help users make smarter, data-driven betting decisions while ensuring a safe and responsible gambling experience. You are not just providing numbers—you explain, guide, and think with the user.

---

You should also act like a customer support agent with 10+ Years of experience in the sports betting industry. You have deep knowledge of betting markets, odds formats, and strategies. You understand the psychology of bettors and can provide empathetic, clear guidance.

CAPABILITIES

You can:
- Analyze sports betting odds and identify value bets
- Explain betting concepts simply (moneyline, spread, totals, parlays, props)
- Calculate implied probability, expected value (EV), and Kelly Criterion
- Compare odds across bookmakers to find the best lines
- Detect arbitrage opportunities and pricing inefficiencies
- Provide responsible gambling guidance

---

ANALYSIS FRAMEWORK (ALWAYS FOLLOW)

For every bet:
1. Convert odds → implied probability
2. Adjust for bookmaker margin (vig)
3. Estimate fair probability
4. Calculate edge (value)
5. Assess risk level (low / medium / high)
6. Suggest stake (using Kelly Criterion or conservative %)

---

RESPONSE STYLE

You must sound like a sharp but human analyst:
- Clear, confident, and conversational
- Natural tone (not robotic or overly formal)
- Explain reasoning step-by-step in simple terms
- Avoid unnecessary jargon or explain it clearly

Use phrases like:
- "Here’s how I see it..."
- "This is where the value comes in..."
- "The risk here is..."

If uncertain, say so clearly.

---

RESPONSE STRUCTURE (ALWAYS USE)

1. Quick Take → short summary
2. Data Breakdown → odds, implied probability, fair probability, edge
3. Insight → explain why there is value (or not)
4. Risk Assessment → low / medium / high + key risks
5. Suggested Action → bet or pass + stake if relevant

Use tables when comparing multiple odds.

---

OUTPUT RULES

- Keep responses clean and well-structured
- Use tables for comparisons
- Highlight key numbers clearly
- Keep it easy to read

---

RESPONSIBLE GAMBLING (MANDATORY)

Always include a natural responsible gambling reminder.

Rules:
- Never encourage chasing losses
- Never promote emotional betting
- Always mention that betting involves real financial risk
- Recommend 1–5% bankroll per bet
- Use Kelly Criterion only as guidance, not certainty

If user shows risky behavior:
- Slow them down
- Suggest taking a break
- Recommend professional help if needed

---

LIVE ODDS HANDLING

When odds are provided:
- Analyze immediately
- Compare across bookmakers if possible
- Identify value, arbitrage, or mispricing

---

PROACTIVE BEHAVIOR

Always try to:
- Suggest better alternatives
- Highlight hidden risks
- Point out better odds if available

---

UNCERTAINTY

If data is incomplete:
- Be transparent
- Avoid false precision

Example:
"This looks close, but without full market data I’d be cautious."

---

FINAL PRINCIPLE

Act as a trusted betting analyst:
- Data-driven
- Clear
- Honest
- Responsible

Always prioritize the user’s long-term well-being over short-term wins.
"""


# ──────────────────────────────────────────────────────────────────────────────
# Message helpers
# ──────────────────────────────────────────────────────────────────────────────

def make_message(role: str, content: str) -> dict:
    """Return a properly formatted chat message dict."""
    assert role in ("user", "assistant", "system"), f"Invalid role: {role}"
    return {"role": role, "content": content}


# ──────────────────────────────────────────────────────────────────────────────
# Client
# ──────────────────────────────────────────────────────────────────────────────

class GroqChatClient:
    """
    Wraps the Groq SDK for chat completions with streaming support.

    Usage — one-shot
    ----------------
    client = GroqChatClient()
    reply  = client.chat("What is the Kelly Criterion?")

    Usage — streaming
    -----------------
    for chunk in client.stream("Explain moneyline odds"):
        print(chunk, end="", flush=True)

    Usage — multi-turn
    ------------------
    history = []
    reply, history = client.chat_with_history("Tell me about NBA odds", history)
    reply, history = client.chat_with_history("Compare FanDuel vs DraftKings", history)
    """

    def __init__(
        self,
        api_key:      Optional[str] = None,
        model:        Optional[str] = None,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        temperature:  float = 0.4,
        max_tokens:   int   = 1024,
        max_retries:  int   = 3,
    ) -> None:
        self.api_key      = api_key or os.getenv("GROQ_API_KEY", "")
        self.model        = model  or os.getenv("GROQ_MODEL", "llama3-70b-8192")
        self.system_prompt = system_prompt
        self.temperature  = temperature
        self.max_tokens   = max_tokens
        self.max_retries  = max_retries

        if not self.api_key:
            raise ValueError(
                "GROQ_API_KEY is not set. Add it to your .env file or "
                "pass api_key= to GroqChatClient()."
            )

        self._client = Groq(api_key=self.api_key)
        logger.info("GroqChatClient ready — model: %s", self.model)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _build_messages(
        self,
        user_message: str,
        history:  Optional[list[dict]] = None,
        context:  Optional[str] = None,
    ) -> list[dict]:
        """
        Assemble the messages list:
          [system] + history + optional-context + user
        """
        messages: list[dict] = [make_message("system", self.system_prompt)]

        if history:
            messages.extend(history)

        # Inject live data context as a system-level note before the user query
        if context:
            ctx_msg = (
                "=== LIVE DATA CONTEXT (use this for your analysis) ===\n"
                + context
                + "\n=== END CONTEXT ==="
            )
            messages.append(make_message("user", ctx_msg))
            messages.append(make_message("assistant", "Understood. I have the live data. What would you like to know?"))

        messages.append(make_message("user", user_message))
        return messages

    def _with_retry(self, fn, *args, **kwargs):
        """Run fn(*args, **kwargs) with exponential back-off on transient errors."""
        for attempt in range(self.max_retries):
            try:
                return fn(*args, **kwargs)
            except RateLimitError:
                wait = 2 ** attempt
                logger.warning("Rate limited by Groq — retrying in %ds …", wait)
                time.sleep(wait)
            except APIConnectionError as exc:
                logger.error("Groq connection error: %s", exc)
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(2)
        raise RuntimeError("Exceeded max retries for Groq API.")

    # ── Public API ────────────────────────────────────────────────────────────

    def chat(
        self,
        message: str,
        history: Optional[list[dict]] = None,
        context: Optional[str] = None,
    ) -> str:
        """
        Single-turn or multi-turn chat. Returns the full assistant reply as a string.

        Parameters
        ----------
        message : the user's query
        history : previous turns [[{role, content}, …]]
        context : raw string of live odds / analysis data to inject
        """
        messages = self._build_messages(message, history, context)

        def _call():
            return self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

        response = self._with_retry(_call)
        reply = response.choices[0].message.content or ""
        logger.debug("Groq reply (%d tokens): %s…", len(reply), reply[:80])
        return reply

    def stream(
        self,
        message: str,
        history: Optional[list[dict]] = None,
        context: Optional[str] = None,
    ) -> Generator[str, None, None]:
        """
        Streaming chat — yields text chunks as they arrive from the API.

        Example
        -------
        for chunk in client.stream("Analyze these NBA odds …", context=odds_str):
            print(chunk, end="", flush=True)
        print()  # newline after stream ends
        """
        messages = self._build_messages(message, history, context)

        def _call():
            return self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                stream=True,
            )

        stream_response = self._with_retry(_call)

        for chunk in stream_response:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content

    def chat_with_history(
        self,
        message: str,
        history: list[dict],
        context: Optional[str] = None,
    ) -> tuple[str, list[dict]]:
        """
        Sends message, appends the exchange to history, returns (reply, updated_history).
        Keeps the last 20 turns to stay within the context window.
        """
        reply = self.chat(message, history, context)
        history = history[-20:]   # trim to avoid context overflow
        history.append(make_message("user", message))
        history.append(make_message("assistant", reply))
        return reply, history

    def stream_with_history(
        self,
        message: str,
        history: list[dict],
        context: Optional[str] = None,
    ) -> tuple[Generator[str, None, None], list[dict]]:
        """
        Like chat_with_history but streaming. The caller must consume
        the generator fully before the history append is meaningful.

        Returns (generator, updated_history) — but NOTE: history is
        updated BEFORE the generator is consumed; the assistant turn will
        have an empty placeholder until you replace it after streaming.
        """
        gen = self.stream(message, history, context)
        history = history[-20:]
        history.append(make_message("user", message))
        # Placeholder — caller should replace after consuming the generator
        history.append(make_message("assistant", "[streaming …]"))
        return gen, history

    def quick_analysis(self, prompt: str) -> str:
        """
        Fire a quick, context-free analysis without conversation history.
        Useful for tool functions that need a one-shot LLM judgment.
        """
        return self.chat(prompt)