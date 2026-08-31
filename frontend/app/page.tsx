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
        // eslint-disable-next-line no-console
        console.debug("[agent event]", ev);
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
    <div className="min-h-screen flex flex-col">
      <header className="px-8 h-20 flex items-center justify-between">
        <span className="text-3xl font-bold tracking-tight text-[var(--text)]">
          Skylark
        </span>
        <button
          onClick={newChat}
          className="bg-[var(--text)] text-[var(--bg)] hover:opacity-90 transition-opacity text-base font-medium rounded-full px-6 py-2.5"
        >
          New chat
        </button>
      </header>

      <main className="flex-1 flex flex-col max-w-3xl w-full mx-auto px-6">
        <div ref={scrollRef} className="flex-1 overflow-y-auto py-8 space-y-6">
          {messages.length === 0 && (
            <div className="mt-24 space-y-8">
              <div className="text-center">
                <h1 className="text-3xl font-semibold tracking-tight text-[var(--text)]">
                  What do you want to know?
                </h1>
              </div>
              <div className="grid gap-2 max-w-xl mx-auto">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => send(s)}
                    className="text-left text-sm text-[var(--text)] bg-[var(--panel)] border border-[var(--border)] hover:bg-[#e8e1d0] rounded-xl px-4 py-3 transition-colors"
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
          className="pb-8 pt-4"
        >
          <div
            className="
              flex items-center gap-2
              bg-white border border-[var(--border)]
              rounded-2xl p-2 pl-1
              shadow-[0_4px_16px_-4px_rgba(28,25,23,0.08),0_2px_4px_-1px_rgba(28,25,23,0.04)]
              focus-within:shadow-[0_10px_28px_-6px_rgba(28,25,23,0.14),0_4px_8px_-2px_rgba(28,25,23,0.06)]
              focus-within:border-[var(--text)]
              transition-all duration-200
            "
          >
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about pipeline, deals, work orders…"
              disabled={busy}
              className="flex-1 bg-transparent px-4 py-3 text-base text-[var(--text)] placeholder:text-[var(--muted)] focus:outline-none disabled:opacity-60"
            />
            {(busy || input.trim()) && (
              <button
                type="submit"
                disabled={busy || !input.trim()}
                aria-label="Send"
                className="
                  bg-[var(--text)] text-[var(--bg)]
                  hover:opacity-90 transition-opacity
                  rounded-xl w-10 h-10 flex items-center justify-center shrink-0
                  disabled:opacity-40
                "
              >
                {busy ? (
                  <span className="inline-flex gap-0.5">
                    <span className="w-1 h-1 rounded-full bg-current animate-pulse" />
                    <span className="w-1 h-1 rounded-full bg-current animate-pulse [animation-delay:150ms]" />
                    <span className="w-1 h-1 rounded-full bg-current animate-pulse [animation-delay:300ms]" />
                  </span>
                ) : (
                  <svg
                    width="18"
                    height="18"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="M12 19V5" />
                    <path d="M5 12l7-7 7 7" />
                  </svg>
                )}
              </button>
            )}
          </div>
        </form>
      </main>
    </div>
  );
}
