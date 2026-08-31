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

  const findEventBoundary = (s: string): number => {
    // SSE spec uses CRLF but many servers emit LF; accept both.
    const idxs = [s.indexOf("\n\n"), s.indexOf("\r\n\r\n")].filter((i) => i >= 0);
    return idxs.length ? Math.min(...idxs) : -1;
  };
  const boundaryLen = (s: string, at: number): number =>
    s.slice(at, at + 4) === "\r\n\r\n" ? 4 : 2;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sep: number;
    while ((sep = findEventBoundary(buffer)) !== -1) {
      const chunk = buffer.slice(0, sep);
      buffer = buffer.slice(sep + boundaryLen(buffer, sep));

      let eventType = "message";
      const dataLines: string[] = [];
      for (const rawLine of chunk.split(/\r?\n/)) {
        const line = rawLine;
        if (line.startsWith(":")) continue; // comment / heartbeat
        if (line.startsWith("event:")) {
          eventType = line.slice(6).trim();
        } else if (line.startsWith("data:")) {
          // preserve exact payload beyond the optional single leading space
          const raw = line.slice(5);
          dataLines.push(raw.startsWith(" ") ? raw.slice(1) : raw);
        }
      }
      if (dataLines.length === 0) continue;
      const dataStr = dataLines.join("\n");

      let data: Record<string, unknown> = {};
      try {
        data = JSON.parse(dataStr);
      } catch (err) {
        // eslint-disable-next-line no-console
        console.warn("[sse] failed to parse data", err, dataStr);
        continue;
      }
      yield { type: eventType, ...data } as AgentEvent;
    }
  }
}
