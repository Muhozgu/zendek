// src/hooks/useChat.ts
// Drop-in React hook for the BetIQ streaming chat.
//
// Usage:
//   const { messages, send, isLoading, clear } = useChat({ sport: "nba" });
//
//   <button onClick={() => send("What's the best value bet tonight?")}>
//     Ask
//   </button>
//   {messages.map((m, i) => <div key={i}>{m.role}: {m.content}</div>)}

import { useState, useCallback, useRef } from "react";
import { betiqClient } from "../api/betiqClient";
import type { ChatMessage, Sport } from "../types/betiq";

interface UseChatOptions {
  sport?: Sport;
  onError?: (err: Error) => void;
}

interface UseChatReturn {
  messages:  ChatMessage[];
  isLoading: boolean;
  send:      (message: string) => void;
  clear:     () => void;
  abort:     () => void;
}

export function useChat({ sport, onError }: UseChatOptions = {}): UseChatReturn {
  const [messages,  setMessages]  = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  // Ref to hold the abort function returned by chatStream
  const abortRef = useRef<(() => void) | null>(null);

  const send = useCallback(
    (message: string) => {
      if (isLoading || !message.trim()) return;

      // Append user message immediately for snappy UX
      const userMsg: ChatMessage = { role: "user", content: message };
      setMessages((prev) => [...prev, userMsg]);
      setIsLoading(true);

      // Add empty assistant message as placeholder — we'll stream into it
      const assistantPlaceholder: ChatMessage = { role: "assistant", content: "" };
      setMessages((prev) => [...prev, assistantPlaceholder]);

      // Build Groq-format history (exclude the placeholder we just added)
      const history = [...messages, userMsg];

      let accumulated = "";

      abortRef.current = betiqClient.chatStream(
        message,
        history,
        sport,
        // onChunk — append each streamed token into the last message
        (chunk) => {
          accumulated += chunk;
          setMessages((prev) => {
            const updated = [...prev];
            updated[updated.length - 1] = {
              role: "assistant",
              content: accumulated,
            };
            return updated;
          });
        },
        // onDone
        () => {
          setIsLoading(false);
          abortRef.current = null;
        },
        // onError
        (err) => {
          setIsLoading(false);
          abortRef.current = null;
          // Replace placeholder with error message
          setMessages((prev) => {
            const updated = [...prev];
            updated[updated.length - 1] = {
              role: "assistant",
              content: "Sorry, something went wrong. Please try again.",
            };
            return updated;
          });
          onError?.(err);
        }
      );
    },
    [messages, isLoading, sport, onError]
  );

  const abort = useCallback(() => {
    abortRef.current?.();
    abortRef.current = null;
    setIsLoading(false);
  }, []);

  const clear = useCallback(() => {
    abort();
    setMessages([]);
  }, [abort]);

  return { messages, isLoading, send, clear, abort };
}