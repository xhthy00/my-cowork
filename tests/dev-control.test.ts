import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import { expect, it, vi } from 'vitest';

it('cancel does not announce completion while the actual reload is still pending', async () => {
  // Exercise the main-process IPC handler without launching Electron or copying
  // its dispatch logic into the test.
  const source = readFileSync(new URL('../electron/main.ts', import.meta.url), 'utf8');
  const block = source.slice(source.indexOf('if (developerControl) {'), source.indexOf('function registerLocalfileProtocol'));
  let handler: (message: { command: string }) => Promise<void> = () => Promise.resolve();
  let finish!: () => void;
  const send = vi.fn(), cancel = vi.fn();
  vm.runInNewContext(ts.transpile(block), {
    developerControl: true,
    process: { connected: true, send, on: (_event: string, callback: typeof handler) => { handler = callback; }, once: vi.fn() },
    lifecycle: { cancel },
    startBackend: () => new Promise<void>(resolve => { finish = resolve; }),
    console,
  });
  const reload = handler({ command: 'reload' });
  await handler({ command: 'cancel' });
  expect(cancel).toHaveBeenCalledOnce();
  expect(send).not.toHaveBeenCalled();
  finish(); await reload;
  expect(send).toHaveBeenCalledExactlyOnceWith({ done: true });
});
