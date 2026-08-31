"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage } from "../app/types";
import { ToolCallCard } from "./ToolCallCard";

export function Message({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={
          isUser
            ? "max-w-[85%] rounded-2xl px-4 py-2 bg-neutral-800 text-neutral-100"
            : "max-w-[90%] w-full text-neutral-100"
        }
      >
        {msg.toolCalls.map((tc) => (
          <ToolCallCard key={tc.id} call={tc} />
        ))}
        {msg.text && (
          <div className="md-content text-[15px] leading-relaxed">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.text}</ReactMarkdown>
          </div>
        )}
        {msg.streaming && !msg.text && msg.toolCalls.length === 0 && (
          <div className="text-neutral-500 text-sm italic">thinking…</div>
        )}
        {msg.error && (
          <div className="text-red-400 text-sm mt-2">Error: {msg.error}</div>
        )}
      </div>
    </div>
  );
}
