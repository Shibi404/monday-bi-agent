"use client";

import { useEffect, useRef, useState } from "react";
import { DialogBox } from "../components/DialogBox";
import { Message } from "../components/Message";
import { ModelPicker, type ModelOption } from "../components/ModelPicker";
import { streamChat } from "./stream";
import type { ChatMessage, ToolCall } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const SUGGESTIONS = [
  "How's our pipeline looking for the energy sector this quarter?",
  "What's the total open deal value by sector?",
  "Which work orders are overdue or blocked?",
  "Prepare a leadership update for this week.",
];

const MODELS: ModelOption[] = [
  { id: "gemini-3.6-flash", label: "Gemini 3.6 Flash" },
];

function newId() {
  return Math.random().toString(36).slice(2, 10);
}

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [convId, setConvId] = useState<string | undefined>(undefined);
  const [selectedModel, setSelectedModel] = useState(MODELS[0].id);
  const [confirmNewChat, setConfirmNewChat] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  // Using `any` for the Web Speech API — types aren't in the TS DOM lib
  // and only two browsers implement it consistently (Chromium + Safari).
  const recognitionRef = useRef<any>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  function toggleMic() {
    const SR =
      typeof window !== "undefined" &&
      ((window as any).SpeechRecognition ||
        (window as any).webkitSpeechRecognition);
    if (!SR) {
      alert("Voice input isn't supported in this browser. Try Chrome or Edge.");
      return;
    }
    if (listening) {
      recognitionRef.current?.stop();
      return;
    }
    const rec = new SR();
    rec.continuous = false;
    rec.interimResults = true;
    rec.lang = "en-US";
    rec.onresult = (e: any) => {
      let t = "";
      for (let i = 0; i < e.results.length; i++) t += e.results[i][0].transcript;
      setInput(t);
    };
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    recognitionRef.current = rec;
    setListening(true);
    rec.start();
  }

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
    } catch {
      setMessages((all) => {
        const next = [...all];
        const idx = next.findIndex((m) => m.id === assistantMsg.id);
        if (idx >= 0) {
          next[idx] = {
            ...next[idx],
            streaming: false,
            error:
              "Couldn't reach the service. Check your connection and try again.",
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
          onClick={() => {
            if (messages.length === 0) {
              newChat();
            } else {
              setConfirmNewChat(true);
            }
          }}
          className="bg-[var(--text)] text-[var(--bg)] hover:opacity-90 transition-opacity text-base font-medium rounded-xl px-6 py-2.5"
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
              rounded-xl p-2 pl-1
              shadow-[0_0_24px_0_rgba(28,25,23,0.08)]
              focus-within:shadow-[0_0_36px_2px_rgba(28,25,23,0.14)]
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
            <ModelPicker
              models={MODELS}
              value={selectedModel}
              onChange={setSelectedModel}
            />
            <button
              type="button"
              onClick={toggleMic}
              aria-label={listening ? "Stop recording" : "Start voice input"}
              className={`
                rounded-xl w-10 h-10 flex items-center justify-center shrink-0
                transition-all duration-150
                ${
                  listening
                    ? "bg-red-500 text-white shadow-[0_0_0_5px_rgba(239,68,68,0.18)] animate-pulse"
                    : "bg-[var(--panel)] text-[var(--text)] shadow-[0_1px_2px_rgba(28,25,23,0.06)] hover:bg-[#e4ddce] hover:shadow-[0_3px_10px_-2px_rgba(28,25,23,0.15)] hover:-translate-y-px active:translate-y-0"
                }
              `}
            >
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <rect x="9" y="2" width="6" height="12" rx="3" />
                <path d="M5 10v2a7 7 0 0 0 14 0v-2" />
                <line x1="12" y1="19" x2="12" y2="22" />
              </svg>
            </button>
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

      <DialogBox
        open={confirmNewChat}
        title="Start a new chat?"
        description="Your current conversation and its cached data will be wiped. This action can't be undone."
        confirmLabel="New chat"
        cancelLabel="Cancel"
        onConfirm={() => {
          setConfirmNewChat(false);
          newChat();
        }}
        onCancel={() => setConfirmNewChat(false)}
      />
    </div>
  );
}
