import { describe, expect, it, vi } from "vitest";
import { createHost } from "../packages/app-sdk/src/index";

function connection() {
  const callbacks = new Set<(event: MessageEvent) => void>();
  const parent = { postMessage: vi.fn() };
  const surface = { parent, location: { search: '?bridge=secret', hostname: 'cn.test.app' },
    addEventListener: (_: string, cb: any) => callbacks.add(cb),
    removeEventListener: (_: string, cb: any) => callbacks.delete(cb) };
  const host = createHost({ appId: 'cn.test.app', targetOrigin: 'http://host', window: surface as any, timeoutMs: 10 });
  const emit = (data: any, origin = 'http://host') => callbacks.forEach(cb => cb({ source: parent, origin, data: { channel: 'mycowork-app/v1', appId: 'cn.test.app', bridgeToken: 'secret', ...data } } as any));
  return { host, parent, callbacks, emit };
}

describe('app SDK lifecycle', () => {
  it('rejects foreign messages and resolves only the matching response', async () => {
    const { host, parent, emit } = connection();
    const pending = host.request('GET', '/records');
    const message = parent.postMessage.mock.calls.at(-1)![0];
    emit({ type: 'response', id: message.id, ok: true, data: 'foreign' }, 'http://foreign');
    emit({ type: 'response', id: message.id, ok: true, data: [1] });
    await expect(pending).resolves.toEqual([1]);
    host.dispose();
  });
  it('does not retry a write whose response was lost', async () => {
    const { host, parent } = connection();
    const pending = host.request('POST', '/records', { title: 'once' });
    await expect(pending).rejects.toThrow('结果尚未确认');
    expect(parent.postMessage.mock.calls.filter(([m]) => m.operation === 'app.request')).toHaveLength(1);
    host.dispose();
  });
  it('disposal removes listeners and settles old requests', async () => {
    const { host, callbacks } = connection();
    const pending = host.request('GET', '/records');
    host.dispose();
    await expect(pending).rejects.toThrow('连接已结束');
    expect(callbacks.size).toBe(0);
  });
});
