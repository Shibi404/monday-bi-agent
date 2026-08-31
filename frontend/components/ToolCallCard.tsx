"use client";

import { useState } from "react";
import type { ToolCall } from "../app/types";

const TOOL_LABEL: Record<string, string> = {
  list_boards: "Listed boards",
  get_board_schema: "Read board schema",
  query_board: "Queried board",
  run_analysis: "Ran analysis",
  ask_user: "Asked for clarification",
};

function friendlySummary(call: ToolCall): string {
  const input = call.input || {};
  const result = call.result || {};
  switch (call.name) {
    case "query_board":
      return `${input.board ?? "board"}${
        typeof result.row_count === "number" ? ` — ${result.row_count} rows` : ""
      }`;
    case "get_board_schema":
      return String(input.board ?? "");
    case "run_analysis": {
      const code = String(input.code ?? "");
      const first = code.split("\n").find((l) => l.trim()) ?? "";
      return first.length > 60 ? first.slice(0, 60) + "…" : first;
    }
    case "ask_user":
      return String(input.question ?? "");
    default:
      return "";
  }
}

export function ToolCallCard({ call }: { call: ToolCall }) {
  const [open, setOpen] = useState(false);
  const label = TOOL_LABEL[call.name] ?? call.name;
  const summary = friendlySummary(call);
  const done = call.result !== undefined;
  const err = call.isError;

  return (
    <div className="my-2 rounded-md border border-neutral-800 bg-neutral-900/60 text-xs">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full text-left px-3 py-2 flex items-center gap-2 hover:bg-neutral-900"
      >
        <span
          className={`inline-block w-2 h-2 rounded-full ${
            err
              ? "bg-red-500"
              : done
              ? "bg-emerald-500"
              : "bg-amber-400 animate-pulse"
          }`}
        />
        <span className="text-neutral-300 font-medium">{label}</span>
        {summary && (
          <span className="text-neutral-500 truncate">
            <span className="text-neutral-600 mx-1">·</span>
            {summary}
          </span>
        )}
        <span className="ml-auto text-neutral-600">{open ? "−" : "+"}</span>
      </button>
      {open && (
        <div className="px-3 pb-3 space-y-2 border-t border-neutral-800">
          <div>
            <div className="text-neutral-500 mt-2 mb-1">Input</div>
            <pre className="whitespace-pre-wrap break-words bg-neutral-950 p-2 rounded text-neutral-300 overflow-x-auto">
              {JSON.stringify(call.input, null, 2)}
            </pre>
          </div>
          {call.result !== undefined && (
            <div>
              <div className="text-neutral-500 mb-1">
                Result{err ? " (error)" : ""}
              </div>
              <pre className="whitespace-pre-wrap break-words bg-neutral-950 p-2 rounded text-neutral-300 overflow-x-auto max-h-80">
                {JSON.stringify(call.result, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
