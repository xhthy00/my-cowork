/** Per-task SSE AbortControllers — Eigent-aligned: switch sessions without aborting. */

const controllers = new Map<string, AbortController>();

export function trackChatStream(
  taskId: string,
  controller: AbortController,
): void {
  const prev = controllers.get(taskId);
  if (prev && prev !== controller) prev.abort();
  controllers.set(taskId, controller);
  controller.signal.addEventListener(
    "abort",
    () => {
      if (controllers.get(taskId) === controller) controllers.delete(taskId);
    },
    { once: true },
  );
}

export function abortChatStream(taskId: string): void {
  const c = controllers.get(taskId);
  if (!c) return;
  c.abort();
  controllers.delete(taskId);
}

export function abortAllChatStreams(): void {
  for (const c of controllers.values()) {
    c.abort();
  }
  controllers.clear();
}

/** Abort every tracked stream (delete space / teardown). */
export function abortActiveChatStream(): void {
  abortAllChatStreams();
}
