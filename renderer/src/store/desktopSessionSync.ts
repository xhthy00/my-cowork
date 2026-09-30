import { apiFetch as fetch } from "@/api/backend";
/** Backend is the durable copy; localStorage remains a fast offline cache. */
import { ensureActiveSession, useSessionsStore } from "./sessions";
import { useSpacesStore } from "./spaces";

const DIRTY_KEY = "my-cowork-desktop-sessions-dirty";
let unsubscribe: (() => void) | null = null;
let backendUrl = "";
let applyingRemote = false;
let revision = 0;
let timer: ReturnType<typeof setTimeout> | null = null;
let writing = false;
let bootPromise: Promise<void> | null = null;

function currentSnapshot() {
  const { sessions, activeId, messagesById } = useSessionsStore.getState();
  const { spaces, activeSpaceId } = useSpacesStore.getState();
  return { sessions, activeId, messagesById, spaces, activeSpaceId };
}

async function flush() {
  if (!backendUrl || writing) return;
  writing = true;
  try {
    while (backendUrl && localStorage.getItem(DIRTY_KEY) === "1") {
      const at = revision;
      const response = await fetch(`${backendUrl}/api/desktop/sessions`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(currentSnapshot()),
      });
      if (!response.ok) break;
      if (at === revision) localStorage.removeItem(DIRTY_KEY);
    }
  } catch {
    // Keep the dirty marker for the timed retry and any backend reconnect.
  } finally {
    writing = false;
    if (backendUrl && localStorage.getItem(DIRTY_KEY) === "1") {
      setTimeout(() => void flush(), 3000);
    }
  }
}

export function initDesktopSessionSync() {
  if (unsubscribe) return;
  const changed = () => {
    if (applyingRemote) return;
    revision += 1;
    localStorage.setItem(DIRTY_KEY, "1");
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => void flush(), 250);
  };
  unsubscribe = useSessionsStore.subscribe(changed);
  useSpacesStore.subscribe(changed);
}

export async function connectDesktopSessionSync(url: string) {
  initDesktopSessionSync();
  if (bootPromise) return bootPromise;
  bootPromise = (async () => {
    try {
      const response = await fetch(`${url}/api/desktop/sessions`);
      if (!response.ok) throw new Error(`Session load failed: ${response.status}`);
      const data = await response.json() as { snapshot?: ReturnType<typeof currentSnapshot> | null };
      if (data.snapshot && localStorage.getItem(DIRTY_KEY) !== "1") {
        applyingRemote = true;
        try {
          if (data.snapshot.spaces?.length) {
            useSpacesStore.getState().replaceSnapshot(data.snapshot.spaces, data.snapshot.activeSpaceId);
          }
          useSessionsStore.getState().replaceSnapshot(data.snapshot);
        }
        finally { applyingRemote = false; }
        if (JSON.stringify(currentSnapshot()) !== JSON.stringify(data.snapshot)) {
          localStorage.setItem(DIRTY_KEY, "1");
        }
      } else {
        localStorage.setItem(DIRTY_KEY, "1");
      }
      backendUrl = url;
      ensureActiveSession();
      await flush();
    } catch {
      backendUrl = "";
      if (useSessionsStore.getState().sessions.length) ensureActiveSession();
      setTimeout(() => {
        void window.api.getBackendUrl().then((nextUrl) => {
          if (nextUrl) void connectDesktopSessionSync(nextUrl);
        }).catch(() => {});
      }, 3000);
    }
  })().finally(() => { bootPromise = null; });
  return bootPromise;
}
