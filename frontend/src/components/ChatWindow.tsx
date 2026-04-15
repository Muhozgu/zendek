// src/components/ChatWindow.tsx
// Example component — adapt the JSX to match your existing frontend design.
// This shows exactly how to wire useChat into your UI.

import { useState, useRef, useEffect } from "react";
import { useChat } from "../hooks/useChat";
import type { Sport } from "../types/betiq";

const SPORTS: { label: string; value: Sport }[] = [
  { label: "None",    value: "nba" },   // placeholder — replace with your UI
  { label: "NBA",     value: "nba" },
  { label: "NFL",     value: "nfl" },
  { label: "EPL",     value: "epl" },
  { label: "NHL",     value: "nhl" },
  { label: "MLB",     value: "mlb" },
];

export function ChatWindow() {
  const [sport,     setSport]     = useState<Sport | undefined>(undefined);
  const [input,     setInput]     = useState("");
  const bottomRef                 = useRef<HTMLDivElement>(null);

  const { messages, isLoading, send, clear } = useChat({ sport });

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function handleSend() {
    if (!input.trim()) return;
    send(input.trim());
    setInput("");
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="flex flex-col h-full">

      {/* Sport selector */}
      <div className="flex items-center gap-2 p-3 border-b border-gray-200">
        <span className="text-sm text-gray-500">Sport context:</span>
        <select
          value={sport ?? ""}
          onChange={(e) => setSport((e.target.value as Sport) || undefined)}
          className="text-sm border rounded px-2 py-1"
        >
          <option value="">None (general chat)</option>
          {SPORTS.slice(1).map((s) => (
            <option key={s.value} value={s.value}>{s.label}</option>
          ))}
        </select>
        <button
          onClick={clear}
          className="ml-auto text-xs text-gray-400 hover:text-gray-600"
        >
          Clear chat
        </button>
      </div>

      {/* Message list */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <p className="text-center text-gray-400 text-sm mt-8">
            Ask BetIQ anything about sports betting odds, value bets, or Kelly sizing.
          </p>
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[80%] rounded-lg px-4 py-2 text-sm whitespace-pre-wrap ${
                msg.role === "user"
                  ? "bg-blue-600 text-white"
                  : "bg-gray-100 text-gray-900"
              }`}
            >
              {msg.content}
              {/* Blinking cursor while streaming the last assistant message */}
              {isLoading && i === messages.length - 1 && msg.role === "assistant" && (
                <span className="inline-block w-1.5 h-4 bg-gray-500 ml-0.5 animate-pulse" />
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div className="border-t border-gray-200 p-3 flex gap-2">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about odds, value bets, Kelly sizing…"
          rows={1}
          className="flex-1 resize-none border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
        <button
          onClick={handleSend}
          disabled={isLoading || !input.trim()}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm disabled:opacity-40 hover:bg-blue-700"
        >
          {isLoading ? "…" : "Send"}
        </button>
      </div>

      {/* Responsible gambling footer */}
      <p className="text-center text-xs text-gray-400 py-1 px-4">
        ⚠ Sports betting involves real financial risk. Never bet more than you can afford to lose.
      </p>
    </div>
  );
}