/**
 * Lightweight model connectivity probe used when the Python backend is down.
 */

import type { ModelProvider } from "./models_store";

export interface ValidateInput {
  provider: ModelProvider;
  model: string;
  apiKey?: string;
  baseUrl?: string;
}

export interface ValidateResult {
  ok: boolean;
  error?: string;
  latency_ms?: number;
}

function trimSlash(url: string): string {
  return url.replace(/\/+$/, "");
}

export async function lightweightValidate(input: ValidateInput): Promise<ValidateResult> {
  const started = Date.now();
  const key = input.apiKey?.trim() ?? "";
  const model = input.model.trim();
  if (!model) {
    return { ok: false, error: "模型 ID 不能为空" };
  }

  try {
    if (input.provider === "anthropic") {
      if (!key) return { ok: false, error: "API Key 不能为空" };
      const host = trimSlash(input.baseUrl || "https://api.anthropic.com");
      const res = await fetch(`${host}/v1/messages`, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-api-key": key,
          "anthropic-version": "2023-06-01",
        },
        body: JSON.stringify({
          model,
          max_tokens: 1,
          messages: [{ role: "user", content: "ping" }],
        }),
      });
      if (!res.ok) {
        const text = await res.text().catch(() => "");
        return {
          ok: false,
          error: text.slice(0, 240) || `HTTP ${res.status}`,
          latency_ms: Date.now() - started,
        };
      }
      return { ok: true, latency_ms: Date.now() - started };
    }

    // OpenAI-compatible / local: prefer GET /models; fall back to tiny chat completion.
    const base = trimSlash(input.baseUrl || "https://api.openai.com/v1");
    const headers: Record<string, string> = {};
    if (key) headers.Authorization = `Bearer ${key}`;
    if (base.includes("openrouter.ai")) {
      headers["HTTP-Referer"] = "https://my-cowork.local";
      headers["X-Title"] = "my-cowork";
    }

    const modelsUrl = base.endsWith("/v1") ? `${base}/models` : `${base}/models`;
    const listRes = await fetch(modelsUrl, { headers });
    if (listRes.ok) {
      return { ok: true, latency_ms: Date.now() - started };
    }

    // Some local servers need a completion probe (and a dummy key).
    const chatRes = await fetch(`${base}/chat/completions`, {
      method: "POST",
      headers: {
        ...headers,
        "content-type": "application/json",
        Authorization: headers.Authorization ?? "Bearer ollama",
      },
      body: JSON.stringify({
        model,
        max_tokens: 1,
        messages: [{ role: "user", content: "ping" }],
      }),
    });
    if (!chatRes.ok) {
      const text = await chatRes.text().catch(() => "");
      return {
        ok: false,
        error: text.slice(0, 240) || `HTTP ${chatRes.status}`,
        latency_ms: Date.now() - started,
      };
    }
    return { ok: true, latency_ms: Date.now() - started };
  } catch (err) {
    return {
      ok: false,
      error: err instanceof Error ? err.message : String(err),
      latency_ms: Date.now() - started,
    };
  }
}
