/**
 * SSE client with two flavours:
 * - subscribeSSE: native EventSource for GET endpoints.
 * - postSSE: fetch-based POST SSE for the chat endpoint, which returns a
 *   text/event-stream body.
 *
 * Backend bus events are often flat (``{type, node, ...}``). We normalize
 * them to ``{type, payload}`` so the session store can consume them.
 */
export interface SSEvent {
  type: string;
  payload: Record<string, unknown>;
}

export function normalizeSSEvent(raw: Record<string, unknown>): SSEvent {
  const type = String(raw.type ?? "unknown");
  const { type: _t, payload, ...rest } = raw;
  const nested =
    payload && typeof payload === "object" && !Array.isArray(payload)
      ? (payload as Record<string, unknown>)
      : {};
  return { type, payload: { ...rest, ...nested } };
}

export function subscribeSSE(url: string, onEvent: (event: SSEvent) => void): EventSource {
  const es = new EventSource(url);

  es.onmessage = (event: MessageEvent) => {
    try {
      const parsed = JSON.parse(event.data) as Record<string, unknown>;
      onEvent(normalizeSSEvent(parsed));
    } catch {
      // Ignore non-JSON messages silently.
    }
  };

  return es;
}

function parseSSEEvents(buffer: string): { events: SSEvent[]; remainder: string } {
  const events: SSEvent[] = [];
  const parts = buffer.split("\n\n");
  const remainder = parts.pop() ?? "";

  for (const part of parts) {
    const dataLines: string[] = [];
    for (const line of part.split("\n")) {
      if (line.startsWith("data: ")) {
        dataLines.push(line.slice(6));
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trimStart());
      }
    }
    if (!dataLines.length) continue;
    try {
      const parsed = JSON.parse(dataLines.join("\n")) as Record<string, unknown>;
      events.push(normalizeSSEvent(parsed));
    } catch {
      // Ignore non-JSON messages.
    }
  }

  return { events, remainder };
}

export function postSSE(
  url: string,
  body: Record<string, unknown>,
  onEvent: (event: SSEvent) => void,
  onError?: (message: string) => void,
): AbortController {
  const controller = new AbortController();

  void (async () => {
    try {
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      if (!response.ok) {
        const detail = await response.text().catch(() => "");
        onError?.(
          `请求失败 HTTP ${response.status}${detail ? `：${detail.slice(0, 200)}` : ""}`,
        );
        return;
      }
      if (!response.body) {
        onError?.("请求失败：响应无正文");
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let sawEvent = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const { events, remainder } = parseSSEEvents(buffer);
        buffer = remainder;
        for (const event of events) {
          sawEvent = true;
          onEvent(event);
        }
      }

      if (buffer.trim()) {
        const { events } = parseSSEEvents(buffer + "\n\n");
        for (const event of events) {
          sawEvent = true;
          onEvent(event);
        }
      }

      if (!sawEvent) {
        onError?.("后端没有返回事件，请检查模型配置或稍后重试。");
      }
    } catch (err) {
      if (controller.signal.aborted) return;
      onError?.(err instanceof Error ? err.message : "发送失败：网络错误");
    }
  })();

  return controller;
}
