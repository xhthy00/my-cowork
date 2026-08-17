/**
 * Local Space store — adapted from eigent spaceStore (no cloud Control Server).
 * Spaces own folder bindings; Projects (sessions) hang under a Space.
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";

export type SpaceSourceType = "blank" | "folder";

export interface CoworkSpace {
  id: string;
  name: string;
  sourceType: SpaceSourceType;
  rootPath: string | null;
  createdAt: number;
  updatedAt: number;
}

interface SpacesState {
  spaces: CoworkSpace[];
  activeSpaceId: string | null;
  createBlankSpace: (name?: string) => string;
  createFolderSpace: (name: string, rootPath: string) => string;
  setActiveSpace: (id: string) => void;
  renameSpace: (id: string, name: string) => void;
  deleteSpace: (id: string) => void;
  getActiveSpace: () => CoworkSpace | null;
  defaultWorkdirMode: (spaceId: string) => "direct-write" | "artifact-only";
}

export const DEFAULT_SPACE_ID = "space-local";

function newSpaceId() {
  return `space-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

function ensureDefaultSpace(spaces: CoworkSpace[]): CoworkSpace[] {
  if (spaces.some((s) => s.id === DEFAULT_SPACE_ID)) return spaces;
  const now = Date.now();
  return [
    {
      id: DEFAULT_SPACE_ID,
      name: "本地工作区",
      sourceType: "blank",
      rootPath: null,
      createdAt: now,
      updatedAt: now,
    },
    ...spaces,
  ];
}

export const useSpacesStore = create<SpacesState>()(
  persist(
    (set, get) => ({
      spaces: ensureDefaultSpace([]),
      activeSpaceId: DEFAULT_SPACE_ID,
      createBlankSpace: (name = "空白工作区") => {
        const id = newSpaceId();
        const now = Date.now();
        const space: CoworkSpace = {
          id,
          name,
          sourceType: "blank",
          rootPath: null,
          createdAt: now,
          updatedAt: now,
        };
        set((s) => ({
          spaces: [space, ...s.spaces],
          activeSpaceId: id,
        }));
        void bindScratchOnBackend(id);
        return id;
      },
      createFolderSpace: (name, rootPath) => {
        const id = newSpaceId();
        const now = Date.now();
        const space: CoworkSpace = {
          id,
          name,
          sourceType: "folder",
          rootPath,
          createdAt: now,
          updatedAt: now,
        };
        set((s) => ({
          spaces: [space, ...s.spaces],
          activeSpaceId: id,
        }));
        void bindFolderOnBackend(id, rootPath);
        return id;
      },
      setActiveSpace: (id) => {
        if (!get().spaces.some((s) => s.id === id)) return;
        set({ activeSpaceId: id });
      },
      renameSpace: (id, name) =>
        set((s) => ({
          spaces: s.spaces.map((x) =>
            x.id === id ? { ...x, name, updatedAt: Date.now() } : x,
          ),
        })),
      deleteSpace: (id) => {
        const current = get().spaces;
        if (current.length <= 1) return;
        set((s) => {
          const spaces = s.spaces.filter((x) => x.id !== id);
          if (spaces.length === 0) return s;
          const activeSpaceId =
            s.activeSpaceId === id
              ? spaces[0]?.id ?? null
              : s.activeSpaceId;
          return { spaces, activeSpaceId };
        });
        void unbindOnBackend(id);
      },
      getActiveSpace: () => {
        const s = get();
        return s.spaces.find((x) => x.id === s.activeSpaceId) ?? null;
      },
      defaultWorkdirMode: (spaceId) => {
        const space = get().spaces.find((x) => x.id === spaceId);
        return space?.sourceType === "folder" ? "direct-write" : "artifact-only";
      },
    }),
    {
      name: "my-cowork-spaces",
      version: 1,
      migrate: (persisted) => {
        const state = (persisted || {}) as Partial<SpacesState>;
        return {
          spaces: ensureDefaultSpace(state.spaces || []),
          activeSpaceId: state.activeSpaceId || DEFAULT_SPACE_ID,
        };
      },
    },
  ),
);

async function bindFolderOnBackend(spaceId: string, rootPath: string) {
  try {
    const url = await window.api?.getBackendUrl?.();
    if (!url) return;
    await fetch(`${url}/api/workspace/bind`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ space_id: spaceId, root_path: rootPath }),
    });
  } catch {
    /* best-effort */
  }
}

async function bindScratchOnBackend(spaceId: string) {
  try {
    const url = await window.api?.getBackendUrl?.();
    if (!url) return;
    await fetch(`${url}/api/workspace/scratch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ space_id: spaceId }),
    });
  } catch {
    /* best-effort */
  }
}

async function unbindOnBackend(spaceId: string) {
  try {
    const url = await window.api?.getBackendUrl?.();
    if (!url) return;
    await fetch(`${url}/api/workspace/${encodeURIComponent(spaceId)}`, {
      method: "DELETE",
    });
  } catch {
    /* best-effort */
  }
}
