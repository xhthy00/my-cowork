/** Notify the open memory screen when a conversation changes long-term memory. */
export const MEMORY_CHANGED_EVENT = "my-cowork:memory-changed";

export function announceMemoryChanged(): void {
  window.dispatchEvent(new Event(MEMORY_CHANGED_EVENT));
}
