/**
 * Per-project live stores — Eigent-aligned: each chat keeps its own
 * session / workforce / preview instance. Background SSE writes the
 * target store directly; switching chats never swaps global state.
 */
import { create } from "zustand";
import { useStore, type StoreApi } from "zustand";

import type { Message, SessionState, SessionStoreDeps } from "./session";
import type { PreviewState } from "./preview";
import type { WorkforceState } from "./workforce";

export const IDLE_PROJECT_ID = "__idle__";

export interface ProjectRuntime {
  projectId: string;
  session: StoreApi<SessionState>;
  workforce: StoreApi<WorkforceState>;
  preview: StoreApi<PreviewState>;
}

export const useActiveProjectIdStore = create<{
  id: string;
  setId: (id: string | null) => void;
}>((set) => ({
  id: IDLE_PROJECT_ID,
  setId: (id) => set({ id: id || IDLE_PROJECT_ID }),
}));

export function setActiveProjectRuntime(id: string | null): void {
  useActiveProjectIdStore.getState().setId(id);
}

export function getActiveProjectId(): string {
  return useActiveProjectIdStore.getState().id;
}

const runtimes = new Map<string, ProjectRuntime>();
const persistUnsubs = new Map<string, () => void>();

type SessionFactory = (deps: SessionStoreDeps) => StoreApi<SessionState>;
type WorkforceFactory = () => StoreApi<WorkforceState>;
type PreviewFactory = () => StoreApi<PreviewState>;

let sessionFactory: SessionFactory | null = null;
let workforceFactory: WorkforceFactory | null = null;
let previewFactory: PreviewFactory | null = null;
let persistMessages: (projectId: string, messages: Message[]) => void = () => {};

export function setProjectMessagePersist(
  fn: (projectId: string, messages: Message[]) => void,
): void {
  persistMessages = fn;
}

export type ActiveStoreHook<T> = {
  <U>(selector: (state: T) => U): U;
  getState: StoreApi<T>["getState"];
  setState: StoreApi<T>["setState"];
  subscribe: StoreApi<T>["subscribe"];
  getInitialState: StoreApi<T>["getInitialState"];
};

function bindActiveHook<T>(
  pick: (rt: ProjectRuntime) => StoreApi<T>,
): ActiveStoreHook<T> {
  function useBoundStore<U>(selector: (state: T) => U): U {
    const id = useActiveProjectIdStore((s) => s.id);
    return useStore(pick(getProjectRuntime(id)), selector);
  }
  useBoundStore.getState = () =>
    pick(getProjectRuntime(getActiveProjectId())).getState();
  useBoundStore.setState = ((...args: Parameters<StoreApi<T>["setState"]>) =>
    pick(getProjectRuntime(getActiveProjectId())).setState(
      ...args,
    )) as StoreApi<T>["setState"];
  useBoundStore.subscribe = ((...args: Parameters<StoreApi<T>["subscribe"]>) =>
    pick(getProjectRuntime(getActiveProjectId())).subscribe(
      ...args,
    )) as StoreApi<T>["subscribe"];
  useBoundStore.getInitialState = () =>
    pick(getProjectRuntime(getActiveProjectId())).getInitialState();
  return useBoundStore as ActiveStoreHook<T>;
}

export function registerAndBindSession(
  factory: SessionFactory,
): ActiveStoreHook<SessionState> {
  sessionFactory = factory;
  return bindActiveHook((rt) => rt.session);
}

export function registerAndBindWorkforce(
  factory: WorkforceFactory,
): ActiveStoreHook<WorkforceState> {
  workforceFactory = factory;
  return bindActiveHook((rt) => rt.workforce);
}

export function registerAndBindPreview(
  factory: PreviewFactory,
): ActiveStoreHook<PreviewState> {
  previewFactory = factory;
  return bindActiveHook((rt) => rt.preview);
}

function requireFactories(): {
  session: SessionFactory;
  workforce: WorkforceFactory;
  preview: PreviewFactory;
} {
  if (!sessionFactory || !workforceFactory || !previewFactory) {
    throw new Error("project runtime factories are not registered");
  }
  return {
    session: sessionFactory,
    workforce: workforceFactory,
    preview: previewFactory,
  };
}

function createRuntime(projectId: string): ProjectRuntime {
  const factories = requireFactories();
  const workforce = factories.workforce();
  const preview = factories.preview();
  const session = factories.session({
    getWorkforce: () => workforce.getState(),
    getPreview: () => preview.getState(),
    isProjectActive: () => getActiveProjectId() === projectId,
  });
  if (projectId !== IDLE_PROJECT_ID) {
    const unsub = session.subscribe((state, prev) => {
      if (state.messages !== prev.messages) {
        persistMessages(projectId, state.messages);
      }
    });
    persistUnsubs.set(projectId, unsub);
  }
  return { projectId, session, workforce, preview };
}

export function getProjectRuntime(projectId: string): ProjectRuntime {
  const id = projectId || IDLE_PROJECT_ID;
  let rt = runtimes.get(id);
  if (!rt) {
    rt = createRuntime(id);
    runtimes.set(id, rt);
  }
  return rt;
}

export function peekProjectRuntime(
  projectId: string,
): ProjectRuntime | undefined {
  return runtimes.get(projectId);
}

/** Create (or return) a project runtime; seed messages only on first create. */
export function ensureProjectRuntime(
  projectId: string,
  seedMessages?: Message[],
): ProjectRuntime {
  const existing = runtimes.get(projectId);
  if (existing) return existing;
  const rt = getProjectRuntime(projectId);
  if (seedMessages && seedMessages.length > 0) {
    rt.session.setState({ messages: seedMessages });
  }
  return rt;
}

export function dropProjectRuntime(projectId: string): void {
  persistUnsubs.get(projectId)?.();
  persistUnsubs.delete(projectId);
  runtimes.delete(projectId);
}

export function dropAllProjectRuntimes(): void {
  for (const unsub of persistUnsubs.values()) unsub();
  persistUnsubs.clear();
  runtimes.clear();
  useActiveProjectIdStore.getState().setId(null);
}
