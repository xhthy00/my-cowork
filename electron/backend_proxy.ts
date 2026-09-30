/** Authenticated host transport. Pulling one chunk per IPC keeps streams bounded. */
export type BackendRequest = {
  url: string;
  method?: string;
  headers?: Record<string, string>;
  body?: Uint8Array;
};

type Pending = {
  owner: number;
  controller: AbortController;
  reader?: ReadableStreamDefaultReader<Uint8Array>;
  reading?: boolean;
};

export class BackendProxy {
  private pending = new Map<string, Pending>();

  constructor(private baseUrl: () => string, private token: () => string) {}

  async request(owner: number, id: string, input: BackendRequest) {
    const base = this.baseUrl();
    const url = new URL(input.url);
    if (!base || url.origin !== base || url.username || url.password || url.hash || !url.pathname.startsWith("/api/")) {
      throw new Error("请求不属于当前宿主后端");
    }
    if (!/^[a-zA-Z0-9_-]{1,100}$/.test(id) || this.pending.has(id)) throw new Error("重复或无效请求");
    const method = input.method || "GET";
    if (!["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"].includes(method)) throw new Error("不支持的请求方法");
    const headers = new Headers();
    for (const [key, value] of Object.entries(input.headers || {})) {
      if (["accept", "content-type"].includes(key.toLowerCase())) headers.set(key, value);
    }
    headers.set("X-MyCowork-Industry-Token", this.token());
    const entry: Pending = { owner, controller: new AbortController() };
    this.pending.set(id, entry);
    try {
      const response = await fetch(url.href, {
        method, headers, body: input.body ? Buffer.from(input.body) : undefined,
        signal: entry.controller.signal, redirect: "error",
      });
      if (entry.controller.signal.aborted) {
        await response.body?.cancel();
        throw new Error("请求已取消");
      }
      entry.reader = response.body?.getReader();
      return { status: response.status, statusText: response.statusText, headers: Object.fromEntries(response.headers) };
    } catch (error) {
      this.pending.delete(id);
      throw error;
    }
  }

  private owned(owner: number, id: string) {
    const entry = this.pending.get(id);
    if (!entry || entry.owner !== owner) throw new Error("请求不属于当前窗口或已结束");
    return entry;
  }

  async read(owner: number, id: string): Promise<{ done: boolean; value?: Uint8Array }> {
    const entry = this.owned(owner, id);
    if (entry.reading) throw new Error("不能同时读取同一个流");
    entry.reading = true;
    try {
      const chunk = entry.reader ? await entry.reader.read() : { done: true };
      if (chunk.done) this.pending.delete(id);
      return chunk;
    } catch (error) {
      this.cancel(owner, id);
      throw error;
    } finally {
      entry.reading = false;
    }
  }

  cancel(owner: number, id: string): void {
    if (!this.pending.has(id)) return;
    const entry = this.owned(owner, id);
    this.pending.delete(id);
    entry.controller.abort();
    void entry.reader?.cancel().catch(() => {});
  }

  closeOwner(owner: number): void {
    for (const [id, entry] of this.pending) if (entry.owner === owner) this.cancel(owner, id);
  }
}
