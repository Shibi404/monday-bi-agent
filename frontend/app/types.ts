export type AgentEvent =
  | { type: "start"; conversation_id: string }
  | { type: "text_delta"; text: string }
  | { type: "message_stop"; stop_reason: string }
  | { type: "done" }
  | { type: "error"; message: string };

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  streaming?: boolean;
  error?: string;
}
