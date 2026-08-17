/**
 * Adapted from eigent: src/store/pageTabStore.ts (SessionPreviewSlice / tab kinds).
 */
import { create } from "zustand";
import { fileBasename, normalizeFsPath } from "@/lib/fsPath";

export interface SessionBrowserNavigationState {
  url: string;
  title: string;
  isLoading: boolean;
  canGoBack: boolean;
  canGoForward: boolean;
}

export interface SessionBrowserTab {
  id: string;
  type: "browser";
  title: string;
  url: string;
  webviewId: string;
  navigation: SessionBrowserNavigationState;
  refreshKey?: number;
}

export interface SessionFileTab {
  id: string;
  type: "file";
  title: string;
  path: string;
  refreshKey?: number;
}

export interface SessionChooserTab {
  id: string;
  type: "chooser";
  title: string;
  refreshKey?: number;
}

export interface SessionTerminalTab {
  id: string;
  type: "terminal";
  title: string;
  agentId?: string;
  taskId?: string;
  refreshKey?: number;
}

export type SessionPreviewTab =
  | SessionChooserTab
  | SessionBrowserTab
  | SessionFileTab
  | SessionTerminalTab;

export type PreviewTabKind = Exclude<SessionPreviewTab["type"], "chooser">;

interface PreviewState {
  open: boolean;
  tabs: SessionPreviewTab[];
  activeTabId: string | null;
  /** Absolute paths with unsaved spreadsheet edits. */
  dirtyPaths: Record<string, boolean>;
  setOpen: (open: boolean) => void;
  setActiveTab: (id: string | null) => void;
  addChooser: () => string;
  openBrowser: (url: string, title?: string) => string;
  openFile: (path: string, title?: string) => string;
  openTerminal: (agentId?: string, taskId?: string) => string;
  closeTab: (id: string) => void;
  closeOtherTabs: (id: string) => void;
  closeAllTabs: () => void;
  refreshTab: (id: string) => void;
  updateBrowserNav: (id: string, nav: Partial<SessionBrowserNavigationState>) => void;
  updateFileTab: (
    id: string,
    patch: { path?: string; title?: string },
  ) => void;
  setPathDirty: (path: string, dirty: boolean) => void;
  isPathDirty: (path: string) => boolean;
  handlePreviewEvent: (type: string, payload: Record<string, unknown>) => void;
  reset: () => void;
}

let tabSeq = 0;
function newTabId(prefix: string): string {
  return `${prefix}-${++tabSeq}`;
}

/** Absolute local path → localfile:// URL for embedded webview preview. */
export function toFileUrl(filePath: string): string {
  if (
    filePath.startsWith("localfile://") ||
    filePath.startsWith("http://") ||
    filePath.startsWith("https://") ||
    filePath.startsWith("blob:") ||
    filePath.startsWith("data:")
  ) {
    return filePath;
  }
  let absolute = normalizeFsPath(filePath) || filePath;
  if (filePath.startsWith("file://")) {
    absolute = normalizeFsPath(
      decodeURIComponent(filePath.replace(/^file:\/\//, "")),
    );
    if (/^\/[A-Za-z]:/.test(absolute)) absolute = absolute.slice(1);
  }
  // Only after \uXXXX decode: remaining `\` are Windows separators.
  const normalized = absolute.replace(/\\/g, "/");
  if (/^[A-Za-z]:\//.test(normalized)) {
    const [drive, ...rest] = normalized.split("/");
    const encoded = rest.map(encodeURIComponent).join("/");
    return encoded
      ? `localfile:///${drive}/${encoded}`
      : `localfile:///${drive}/`;
  }
  const encoded = normalized
    .split("/")
    .map((seg, i) => (i === 0 && seg === "" ? "" : encodeURIComponent(seg)))
    .join("/");
  return `localfile://${encoded}`;
}

function isHtmlPath(p: string): boolean {
  return /\.html?$/i.test(fileBasename(p));
}

export const usePreviewStore = create<PreviewState>((set, get) => ({
  open: false,
  tabs: [],
  activeTabId: null,
  dirtyPaths: {},

  setOpen: (open) => set({ open }),

  setActiveTab: (id) => set({ activeTabId: id }),

  setPathDirty: (path, dirty) => {
    const key = normalizeFsPath(path) || path;
    if (!key) return;
    set((s) => {
      const next = { ...s.dirtyPaths };
      if (dirty) next[key] = true;
      else delete next[key];
      return { dirtyPaths: next };
    });
  },

  isPathDirty: (path) => {
    const key = normalizeFsPath(path) || path;
    return Boolean(get().dirtyPaths[key]);
  },

  updateFileTab: (id, patch) =>
    set((s) => ({
      tabs: s.tabs.map((t) => {
        if (t.id !== id || t.type !== "file") return t;
        const path = patch.path != null ? normalizeFsPath(patch.path) || patch.path : t.path;
        return {
          ...t,
          path,
          title: patch.title ?? (patch.path ? fileBasename(path) : t.title),
        };
      }),
    })),

  addChooser: () => {
    const id = newTabId("chooser");
    set((s) => ({
      open: true,
      tabs: [...s.tabs, { id, type: "chooser", title: "新建" }],
      activeTabId: id,
    }));
    return id;
  },

  openBrowser: (url, title) => {
    const id = newTabId("browser");
    const webviewId = `session-preview:default:${id}`;
    set((s) => ({
      open: true,
      tabs: [
        ...s.tabs.filter((t) => t.type !== "chooser"),
        {
          id,
          type: "browser",
          title: title || "浏览器",
          url,
          webviewId,
          navigation: {
            url,
            title: title || url,
            isLoading: false,
            canGoBack: false,
            canGoForward: false,
          },
        },
      ],
      activeTabId: id,
    }));
    return id;
  },

  openFile: (path, title) => {
    // Multi-line path blobs → open each; decode literal \uXXXX escapes.
    const list = path
      .split(/[\r\n]+/)
      .map((p) => normalizeFsPath(p))
      .filter(Boolean);
    let firstId = "";
    for (let i = 0; i < list.length; i++) {
      const p = list[i];
      const name = fileBasename(p) || p;
      const tabTitle = i === 0 && title && list.length === 1 ? title : name;
      // Drop corrupted titles like "u6790.png" from old \u-split bugs.
      const safeTitle =
        tabTitle && /^u[0-9a-fA-F]{4}\./i.test(tabTitle) ? name : tabTitle;
      // HTML deliverables → built-in browser (interactive charts / scripts).
      if (isHtmlPath(p)) {
        const id = get().openBrowser(toFileUrl(p), safeTitle);
        if (i === 0) firstId = id;
        continue;
      }
      const id = newTabId("file");
      if (i === 0) firstId = id;
      set((s) => ({
        open: true,
        tabs: [
          ...s.tabs.filter((t) => t.type !== "chooser"),
          {
            id,
            type: "file",
            title: safeTitle,
            path: p,
          },
        ],
        activeTabId: id,
      }));
    }
    return firstId;
  },

  openTerminal: (agentId, taskId) => {
    const id = newTabId("terminal");
    set((s) => ({
      open: true,
      tabs: [
        ...s.tabs.filter((t) => t.type !== "chooser"),
        {
          id,
          type: "terminal",
          title: agentId ? `终端 · ${agentId}` : "终端",
          agentId,
          taskId,
        },
      ],
      activeTabId: id,
    }));
    return id;
  },

  closeTab: (id) =>
    set((s) => {
      const closing = s.tabs.find((t) => t.id === id);
      const dirtyPaths = { ...s.dirtyPaths };
      if (closing?.type === "file") {
        const key = normalizeFsPath(closing.path) || closing.path;
        delete dirtyPaths[key];
      }
      const tabs = s.tabs.filter((t) => t.id !== id);
      const activeTabId =
        s.activeTabId === id ? (tabs[tabs.length - 1]?.id ?? null) : s.activeTabId;
      return {
        tabs,
        activeTabId,
        dirtyPaths,
        open: tabs.length > 0 ? s.open : false,
      };
    }),

  closeOtherTabs: (id) =>
    set((s) => {
      const keep = s.tabs.find((t) => t.id === id);
      if (!keep) return s;
      const dirtyPaths: Record<string, boolean> = {};
      if (keep.type === "file") {
        const key = normalizeFsPath(keep.path) || keep.path;
        if (s.dirtyPaths[key]) dirtyPaths[key] = true;
      }
      return {
        tabs: [keep],
        activeTabId: keep.id,
        dirtyPaths,
        open: true,
      };
    }),

  closeAllTabs: () =>
    set({
      tabs: [],
      activeTabId: null,
      dirtyPaths: {},
      open: false,
    }),

  refreshTab: (id) =>
    set((s) => ({
      tabs: s.tabs.map((t) =>
        t.id === id ? { ...t, refreshKey: (t.refreshKey ?? 0) + 1 } : t,
      ),
    })),

  updateBrowserNav: (id, nav) =>
    set((s) => ({
      tabs: s.tabs.map((t) =>
        t.id === id && t.type === "browser"
          ? { ...t, navigation: { ...t.navigation, ...nav }, url: nav.url ?? t.url }
          : t,
      ),
    })),

  handlePreviewEvent: (type, payload) => {
    if (type === "preview.open") {
      const kind = String(payload.kind ?? "browser");
      if (kind === "browser" && payload.url) {
        get().openBrowser(String(payload.url));
      } else if (kind === "file" && payload.path) {
        get().openFile(String(payload.path));
      } else if (kind === "terminal") {
        // Prefer assign_id / sub_task_id — payload.task_id is the session run id
        // and would filter PreviewTerminal to an empty task list.
        const assignId =
          payload.assign_id != null
            ? String(payload.assign_id)
            : payload.sub_task_id != null
              ? String(payload.sub_task_id)
              : undefined;
        get().openTerminal(
          payload.agent_id ? String(payload.agent_id) : undefined,
          assignId,
        );
      }
    } else if (type === "artifact.screenshot" && payload.path) {
      get().openFile(String(payload.path), "截图");
    }
  },

  reset: () => set({ open: false, tabs: [], activeTabId: null, dirtyPaths: {} }),
}));
