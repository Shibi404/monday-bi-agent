"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage } from "../app/types";
import { ThinkingIndicator } from "./ThinkingIndicator";

export function Message({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  // While the agent is running tools but hasn't produced text yet,
  // keep the thinking indicator up so the user knows work is happening.
  const showThinking = msg.streaming && !msg.text;

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={
          isUser
            ? "max-w-[85%] rounded-2xl px-4 py-2 bg-[var(--panel)] text-[var(--text)]"
            : "max-w-[90%] w-full text-[var(--text)]"
        }
      >
        {msg.text && (
          <div className="md-content text-[15px] leading-relaxed">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.text}</ReactMarkdown>
          </div>
        )}
        {showThinking && <ThinkingIndicator />}
        {msg.error && (
          <div className="mt-3 rounded-xl bg-[#fce8e4] border border-[#f0c9c1] p-3.5 flex gap-3 items-start">
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="#a63b3b"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="mt-0.5 shrink-0"
              aria-hidden
            >
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <div className="text-sm leading-relaxed text-[#7a2a2a]">
              {msg.error}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
