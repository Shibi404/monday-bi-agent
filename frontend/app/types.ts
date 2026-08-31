export type AgentEvent =
  | { type: "start"; conversation_id: string }
  | { type: "text_delta"; text: string }
  | { type: "tool_use"; id: string; name: string; input: Record<string, unknown> }
  | {
      type: "tool_result";
      id: string;
      name: string;
      content: Record<string, unknown>;
      is_error: boolean;
    }
  | { type: "message_stop"; stop_reason: string }
  | { type: "done" }
  | { type: "error"; message: string };

export interface ToolCall {
  id: string;
  name: string;
  input: Record<string, unknown>;
  result?: Record<string, unknown>;
  isError?: boolean;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  toolCalls: ToolCall[];
  streaming?: boolean;
  error?: string;
}
