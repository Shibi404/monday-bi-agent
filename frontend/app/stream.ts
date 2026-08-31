/**
 * Consumes an SSE stream from POST /chat and yields parsed events.
 *
 * sse-starlette formats each event as:
 *   event: <type>
 *   data: <json>
 *   \n
 */
import type { AgentEvent } from "./types";

export async function* streamChat(
  apiUrl: string,
  body: { message: string; conversation_id?: string },
  signal?: AbortSignal
): AsyncGenerator<AgentEvent> {
  const resp = await fetch(`${apiUrl}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });

  if (!resp.ok || !resp.body) {
    const errText = await resp.text().catch(() => "");
    throw new Error(`chat request failed: ${resp.status} ${errText}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const chunk = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);

      let eventType = "message";
      let dataStr = "";
      for (const line of chunk.split("\n")) {
        if (line.startsWith("event:")) eventType = line.slice(6).trim();
        else if (line.startsWith("data:")) dataStr += line.slice(5).trim();
      }
      if (!dataStr) continue;

      let data: Record<string, unknown> = {};
      try {
        data = JSON.parse(dataStr);
      } catch {
        continue;
      }
      yield { type: eventType, ...data } as AgentEvent;
    }
  }
}
