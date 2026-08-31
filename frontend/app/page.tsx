"use client";

import { useEffect, useRef, useState } from "react";
import { Message } from "../components/Message";
import { streamChat } from "./stream";
import type { ChatMessage, ToolCall } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const SUGGESTIONS = [
  "How's our pipeline looking for the energy sector this quarter?",
  "What's the total open deal value by sector?",
  "Which work orders are overdue or blocked?",
  "Prepare a leadership update for this week.",
];

function newId() {
  return Math.random().toString(36).slice(2, 10);
}

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [convId, setConvId] = useState<string | undefined>(undefined);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || busy) return;

    const userMsg: ChatMessage = {
      id: newId(),
      role: "user",
      text: trimmed,
      toolCalls: [],
    };
    const assistantMsg: ChatMessage = {
      id: newId(),
      role: "assistant",
      text: "",
      toolCalls: [],
      streaming: true,
    };
    setMessages((m) => [...m, userMsg, assistantMsg]);
    setInput("");
    setBusy(true);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      for await (const ev of streamChat(
        API_URL,
        { message: trimmed, conversation_id: convId },
        controller.signal
      )) {
        setMessages((all) => {
          const next = [...all];
          const idx = next.findIndex((m) => m.id === assistantMsg.id);
          if (idx < 0) return next;
          const m = { ...next[idx], toolCalls: [...next[idx].toolCalls] };

          switch (ev.type) {
            case "start":
              setConvId(ev.conversation_id);
              break;
            case "text_delta":
              m.text = m.text + ev.text;
              break;
            case "tool_use":
              m.toolCalls.push({
                id: ev.id,
                name: ev.name,
                input: ev.input,
              });
              break;
            case "tool_result": {
              const call = m.toolCalls.find((c) => c.id === ev.id);
              if (call) {
                call.result = ev.content;
                call.isError = ev.is_error;
              }
              break;
            }
            case "error":
              m.error = ev.message;
              m.streaming = false;
              break;
            case "done":
              m.streaming = false;
              break;
          }
          next[idx] = m;
          return next;
        });
      }
    } catch (err) {
      setMessages((all) => {
        const next = [...all];
        const idx = next.findIndex((m) => m.id === assistantMsg.id);
        if (idx >= 0) {
          next[idx] = {
            ...next[idx],
            streaming: false,
            error: err instanceof Error ? err.message : String(err),
          };
        }
        return next;
      });
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }

  async function newChat() {
    if (convId) {
      try {
        await fetch(`${API_URL}/reset`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ conversation_id: convId }),
        });
      } catch {
        // best effort
      }
    }
    setConvId(undefined);
    setMessages([]);
  }

  return (
    <main className="min-h-screen flex flex-col max-w-3xl mx-auto px-4">
      <header className="flex items-center justify-between py-4 border-b border-neutral-800">
        <div>
          <h1 className="text-lg font-semibold">BI Agent</h1>
          <p className="text-xs text-neutral-500">
            Ask about deals & work orders — data is live from monday.com.
          </p>
        </div>
        <button
          onClick={newChat}
          className="text-xs text-neutral-400 hover:text-neutral-100 px-3 py-1 rounded border border-neutral-800 hover:border-neutral-600"
        >
          New chat
        </button>
      </header>

      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto py-6 space-y-4"
      >
        {messages.length === 0 && (
          <div className="text-center text-neutral-500 mt-16 space-y-4">
            <p className="text-sm">Try one of these:</p>
            <div className="flex flex-col gap-2 items-center">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="text-left text-sm text-neutral-300 border border-neutral-800 hover:border-neutral-600 hover:bg-neutral-900 rounded-lg px-4 py-2 max-w-lg w-full"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m) => (
          <Message key={m.id} msg={m} />
        ))}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        className="border-t border-neutral-800 py-4"
      >
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about pipeline, deals, work orders…"
            disabled={busy}
            className="flex-1 bg-neutral-900 border border-neutral-800 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-neutral-600 disabled:opacity-60"
          />
          <button
            type="submit"
            disabled={busy || !input.trim()}
            className="bg-neutral-100 text-neutral-900 rounded-lg px-4 py-2 text-sm font-medium disabled:opacity-40"
          >
            {busy ? "…" : "Send"}
          </button>
        </div>
      </form>
    </main>
  );
}
