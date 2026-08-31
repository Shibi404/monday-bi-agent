"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage } from "../app/types";

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
            ? "max-w-[85%] rounded-2xl px-4 py-2 bg-neutral-800 text-neutral-100"
            : "max-w-[90%] w-full text-neutral-100"
        }
      >
        {msg.text && (
          <div className="md-content text-[15px] leading-relaxed">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.text}</ReactMarkdown>
          </div>
        )}
        {showThinking && (
          <div className="flex items-center gap-2 text-neutral-500 text-sm">
            <span className="inline-flex gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-neutral-500 animate-pulse" />
              <span className="w-1.5 h-1.5 rounded-full bg-neutral-500 animate-pulse [animation-delay:150ms]" />
              <span className="w-1.5 h-1.5 rounded-full bg-neutral-500 animate-pulse [animation-delay:300ms]" />
            </span>
            <span className="italic">thinking</span>
          </div>
        )}
        {msg.error && (
          <div className="text-red-400 text-sm mt-2">Error: {msg.error}</div>
        )}
      </div>
    </div>
  );
}
