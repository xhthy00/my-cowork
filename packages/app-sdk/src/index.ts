/** Typed client for the existing v1 iframe bridge. No direct host API access. */
export interface TaskInput {
  prompt: string; context?: Record<string, unknown>; tools?: string[];
  skills?: string[]; files?: string[]; produce_file?: boolean;
}
export interface Appearance { theme: 'light' | 'dark'; fontScale: number }
export interface HostOptions {
  appId: string; targetOrigin?: string; window?: Window; timeoutMs?: number;
}
const CHANNEL = 'mycowork-app/v1';

export function createHost(options: HostOptions) {
  const surface = options.window || window;
  const query = new URLSearchParams(surface.location.search);
  const token = query.get('bridge');
  const origin = options.targetOrigin || query.get('hostOrigin') || 'null';
  const target = origin === 'null' || origin === 'file://' ? '*' : origin;
  const pending = new Map<string, { resolve(value: any): void; reject(error: Error): void; timer: ReturnType<typeof setTimeout> }>();
  const subscriptions = new Map<string, Set<(data: any) => void>>();
  let disposed = false;
  let appearance: Appearance = { theme: 'light', fontScale: 1 };
  const message = (event: MessageEvent) => {
    const data = event.data;
    if (event.source !== surface.parent || event.origin !== origin || !data || data.channel !== CHANNEL || data.appId !== options.appId || data.bridgeToken !== token) return;
    if (data.type === 'response') {
      const request = pending.get(data.id);
      if (!request) return;
      clearTimeout(request.timer); pending.delete(data.id);
      if (data.ok) request.resolve(data.data); else request.reject(new Error(data.error || '宿主请求失败'));
    } else {
      if (data.type === 'host.appearance') appearance = { theme: data.theme, fontScale: data.fontScale };
      subscriptions.get(data.type)?.forEach(callback => callback(data));
    }
  };
  surface.addEventListener('message', message);
  function call<T = any>(operation: string, args: Record<string, unknown> = {}): Promise<T> {
    if (disposed) return Promise.reject(new Error('连接已结束，请刷新页面'));
    if (!token) return Promise.reject(new Error('请在 MyCowork 行业工作台打开此页面'));
    const id = crypto.randomUUID();
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        pending.delete(id);
        reject(new Error('宿主未及时响应，结果尚未确认；请检查实际记录，不要重复提交写操作'));
      }, options.timeoutMs ?? (operation === 'files.pick' ? 300_000 : 30_000));
      pending.set(id, { resolve, reject, timer });
      surface.parent.postMessage({ channel: CHANNEL, appId: options.appId, bridgeToken: token, type: 'request', id, operation, ...args }, target);
    });
  }
  function on(type: 'host.appearance' | 'host.ai.changed', callback: (data: any) => void) {
    const listeners = subscriptions.get(type) || new Set();
    listeners.add(callback); subscriptions.set(type, listeners);
    if (type === 'host.appearance') callback(appearance);
    return () => { listeners.delete(callback); };
  }
  void call('ui.ready').catch(() => {});
  return {
    request: <T = any>(method: string, path: string, body?: unknown) => call<T>('app.request', { method, path, body }),
    ai: {
      startTask: (body: TaskInput) => call('ai.startTask', { body }),
      listTasks: () => call('ai.listTasks'), getTask: (task_id: string) => call('ai.getTask', { task_id }),
      stopTask: (task_id: string) => call('ai.stopTask', { task_id }), openTask: (task_id: string) => call('ai.openTask', { task_id }),
    },
    files: { pick: () => call('files.pick'), open: (file_id: string) => call('files.open', { file_id }) },
    navigation: { setRoute: (route: string) => call('navigation.setRoute', { route }) },
    ui: { setDirty: (dirty: boolean) => call('ui.setDirty', { dirty }) }, on,
    dispose() {
      disposed = true; surface.removeEventListener('message', message);
      for (const request of pending.values()) { clearTimeout(request.timer); request.reject(new Error('连接已结束，请刷新页面确认实际记录')); }
      pending.clear(); subscriptions.clear();
    },
  };
}
