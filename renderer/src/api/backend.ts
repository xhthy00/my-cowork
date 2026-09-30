/** Host-only fetch transport. API credentials never enter the renderer or plugin. */
export async function apiFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const api = typeof window !== "undefined" ? window.api : undefined;
  if (!api?.backendRequest) return init === undefined ? globalThis.fetch(input) : globalThis.fetch(input, init);
  const request = new Request(input, init);
  const id = crypto.randomUUID();
  const signal = init?.signal || request.signal;
  const abort = () => { void api.backendCancel(id).catch(() => {}); };
  if (signal.aborted) throw new DOMException("请求已取消", "AbortError");
  signal.addEventListener("abort", abort, { once: true });
  const cleanup = () => signal.removeEventListener("abort", abort);
  try {
    const body = request.body ? new Uint8Array(await request.arrayBuffer()) : undefined;
    if (signal.aborted) throw new DOMException("请求已取消", "AbortError");
    const headers: Record<string, string> = {};
    request.headers.forEach((value, key) => { headers[key] = value; });
    const result = await api.backendRequest(id, {
      url: request.url, method: request.method,
      headers, body,
    });
    if (signal.aborted) throw new DOMException("请求已取消", "AbortError");
    if ([204, 205, 304].includes(result.status) || request.method === "HEAD") {
      cleanup(); abort();
      return new Response(null, result);
    }
    const stream = new ReadableStream<Uint8Array>({
      async pull(controller) {
        try {
          const chunk = await api.backendRead(id);
          if (chunk.done) { cleanup(); controller.close(); }
          else if (chunk.value) controller.enqueue(new Uint8Array(chunk.value));
        } catch (error) { cleanup(); controller.error(error); }
      },
      cancel() { cleanup(); abort(); },
    });
    return new Response(stream, result);
  } catch (error) {
    cleanup(); abort();
    throw error;
  }
}
