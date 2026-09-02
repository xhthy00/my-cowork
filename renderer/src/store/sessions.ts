/**
 * Local Project persistence (formerly ChatSession).
 * Adapted UX from eigent project list — storage is local JSON via localStorage.
 * Projects belong to a Space; messages keyed by project id.
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";

import {
  abortChatStream,
} from "../api/chatStream";
import {
  dropProjectPark,
  getProjectTaskId,
  parkProject,
  restoreProject,
} from "./livePark";
import {
  setActiveProjectRuntime,
  setProjectMessagePersist,
} from "./projectRuntime";
import type { Message } from "./session";

import "./session";
import {
  DEFAULT_SPACE_ID,
  useSpacesStore,
  type CoworkSpace,
} from "./spaces";
import {
  parseBoundKnowledgeBases,
  type BoundKnowledgeBase,
} from "@/lib/knowledgeSources";

export type WorkdirMode =
  | "direct-write"
  | "copy"
  | "worktree"
  | "artifact-only";

/** @deprecated Prefer Project — kept as alias for existing imports */
export type ChatSession = Project;

export interface Project {
  id: string;
  title: string;
  spaceId: string;
  workdirMode: WorkdirMode;
  createdAt: number;
  updatedAt: number;
  status: "idle" | "running" | "done" | "error";
  assistantId?: string;
  /** Stable display name; `title` may become the first user query. */
  assistantName?: string;
  enabledSkillIds?: string[];
  /** Composer-bound IMA libraries; search these by default. */
  boundKnowledgeBases?: BoundKnowledgeBase[];
  /** Recommended prompts from the bound office assistant (Hub cold-start). */
  assistantPrompts?: string[];
}

type CreateProjectOpts = {
  spaceId?: string;
  workdirMode?: WorkdirMode;
  assistantId?: string;
  assistantName?: string;
  enabledSkillIds?: string[];
  assistantPrompts?: string[];
};

interface SessionsState {
  sessions: Project[];
  activeId: string | null;
  messagesById: Record<string, Message[]>;
  createSession: (title?: string, opts?: CreateProjectOpts) => string;
  createProject: (title?: string, opts?: CreateProjectOpts) => string;
  setActive: (id: string) => void;
  renameSession: (id: string, title: string) => void;
  deleteSession: (id: string) => void;
  deleteProject: (id: string) => void;
  touchSession: (id: string, patch?: Partial<Project>) => void;
  setProjectWorkdirMode: (id: string, workdirMode: WorkdirMode) => void;
  saveMessages: (id: string, messages: Message[]) => void;
  getMessages: (id: string) => Message[];
  projectsForSpace: (spaceId: string) => Project[];
  deleteProjectsInSpace: (spaceId: string) => void;
}

function newId() {
  return `s-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

/**
 * Session id that the live chat store is currently bound to.
 * Persist subscription must ignore updates while this is null (mid-switch).
 */
export let liveBoundId: string | null = null;

export function setLiveBoundId(id: string | null): void {
  liveBoundId = id;
}

function abortProjectStream(projectId: string): void {
  const taskId = getProjectTaskId(projectId);
  if (taskId) abortChatStream(taskId);
  dropProjectPark(projectId);
}

/** Hydrate the active project's own store from persisted messages (startup). */
export function hydrateLiveChat(): void {
  const s = useSessionsStore.getState();
  const id = s.activeId;
  if (id) restoreProject(id, s.getMessages(id));
  else setActiveProjectRuntime(null);
  setLiveBoundId(id);
}

function migrateProject(raw: Record<string, unknown>): Project {
  const spaceId =
    typeof raw.spaceId === "string" && raw.spaceId
      ? raw.spaceId
      : DEFAULT_SPACE_ID;
  const workdirMode = (
    ["direct-write", "copy", "worktree", "artifact-only"] as WorkdirMode[]
  ).includes(raw.workdirMode as WorkdirMode)
    ? (raw.workdirMode as WorkdirMode)
    : "artifact-only";
  return {
    id: String(raw.id),
    title: String(raw.title || "新对话"),
    spaceId,
    workdirMode,
    createdAt: Number(raw.createdAt) || Date.now(),
    updatedAt: Number(raw.updatedAt) || Date.now(),
    status: (raw.status as Project["status"]) || "idle",
    assistantId:
      typeof raw.assistantId === "string" ? raw.assistantId : undefined,
    assistantName:
      typeof raw.assistantName === "string"
        ? raw.assistantName
        : typeof raw.assistantId === "string" && typeof raw.title === "string"
          ? String(raw.title)
          : undefined,
    enabledSkillIds: Array.isArray(raw.enabledSkillIds)
      ? raw.enabledSkillIds.map(String)
      : undefined,
    boundKnowledgeBases: parseBoundKnowledgeBases(raw.boundKnowledgeBases),
    assistantPrompts: Array.isArray(raw.assistantPrompts)
      ? raw.assistantPrompts.map(String)
      : undefined,
  };
}

function bindLiveToProject(id: string, get: () => SessionsState) {
  restoreProject(id, get().getMessages(id));
  setLiveBoundId(id);
}

export const useSessionsStore = create<SessionsState>()(
  persist(
    (set, get) => {
      const createProject = (title = "新对话", opts?: CreateProjectOpts) => {
        const spaceId =
          opts?.spaceId ||
          useSpacesStore.getState().activeSpaceId ||
          DEFAULT_SPACE_ID;
        const workdirMode =
          opts?.workdirMode ||
          useSpacesStore.getState().defaultWorkdirMode(spaceId);
        const id = newId();
        const now = Date.now();
        const session: Project = {
          id,
          title,
          spaceId,
          workdirMode,
          createdAt: now,
          updatedAt: now,
          status: "idle",
          assistantId: opts?.assistantId,
          assistantName:
            opts?.assistantId != null
              ? opts.assistantName || title
              : undefined,
          enabledSkillIds: opts?.enabledSkillIds,
          assistantPrompts: opts?.assistantPrompts,
        };
        const prev = get().activeId;
        if (prev) parkProject(prev);
        set((s) => ({
          sessions: [session, ...s.sessions],
          activeId: id,
          messagesById: {
            ...s.messagesById,
            ...(prev
              ? { [prev]: useSessionsStore.getState().getMessages(prev) }
              : {}),
            [id]: [],
          },
        }));
        restoreProject(id, []);
        setLiveBoundId(id);
        return id;
      };

      return {
        sessions: [],
        activeId: null,
        messagesById: {},
        createSession: createProject,
        createProject,
        setActive: (id) => {
          if (get().activeId === id) return;
          const prev = get().activeId;
          if (prev) parkProject(prev);
          set((s) => ({
            activeId: id,
            messagesById: prev
              ? {
                  ...s.messagesById,
                  [prev]: useSessionsStore.getState().getMessages(prev),
                }
              : s.messagesById,
          }));
          const project = get().sessions.find((x) => x.id === id);
          if (project) {
            useSpacesStore.getState().setActiveSpace(project.spaceId);
          }
          bindLiveToProject(id, get);
        },
        renameSession: (id, title) =>
          set((s) => ({
            sessions: s.sessions.map((x) =>
              x.id === id ? { ...x, title, updatedAt: Date.now() } : x,
            ),
          })),
        deleteSession: (id) => {
          const s = get();
          const removed = s.sessions.find((x) => x.id === id);
          const sessions = s.sessions.filter((x) => x.id !== id);
          const { [id]: _removed, ...messagesById } = s.messagesById;
          const nextActive =
            s.activeId === id
              ? sessions.find((x) => x.spaceId === removed?.spaceId)?.id ??
                sessions[0]?.id ??
                null
              : s.activeId;
          abortProjectStream(id);
          if (s.activeId === id) {
            if (nextActive) {
              restoreProject(nextActive, messagesById[nextActive] ?? []);
            } else {
              setActiveProjectRuntime(null);
            }
            setLiveBoundId(nextActive);
            const nextProject = sessions.find((x) => x.id === nextActive);
            if (nextProject) {
              useSpacesStore.getState().setActiveSpace(nextProject.spaceId);
            }
          }
          set({ sessions, activeId: nextActive, messagesById });
        },
        deleteProject: (id) => get().deleteSession(id),
        touchSession: (id, patch) =>
          set((s) => ({
            sessions: s.sessions.map((x) =>
              x.id === id ? { ...x, ...patch, updatedAt: Date.now() } : x,
            ),
          })),
        setProjectWorkdirMode: (id, workdirMode) =>
          set((s) => ({
            sessions: s.sessions.map((x) =>
              x.id === id ? { ...x, workdirMode, updatedAt: Date.now() } : x,
            ),
          })),
        saveMessages: (id, messages) =>
          set((s) => ({
            messagesById: { ...s.messagesById, [id]: messages },
          })),
        getMessages: (id) => get().messagesById[id] ?? [],
        projectsForSpace: (spaceId) =>
          get().sessions.filter((x) => x.spaceId === spaceId),
        deleteProjectsInSpace: (spaceId) => {
          const s = get();
          const removedIds = new Set(
            s.sessions.filter((x) => x.spaceId === spaceId).map((x) => x.id),
          );
          if (removedIds.size === 0) return;
          const sessions = s.sessions.filter((x) => x.spaceId !== spaceId);
          const messagesById = { ...s.messagesById };
          for (const id of removedIds) {
            delete messagesById[id];
          }
          const nextActive =
            s.activeId && removedIds.has(s.activeId)
              ? sessions[0]?.id ?? null
              : s.activeId;
          for (const id of removedIds) abortProjectStream(id);
          if (s.activeId && removedIds.has(s.activeId)) {
            if (nextActive) {
              restoreProject(nextActive, messagesById[nextActive] ?? []);
            } else {
              setActiveProjectRuntime(null);
            }
            setLiveBoundId(nextActive);
          }
          set({ sessions, messagesById, activeId: nextActive });
        },
      };
    },
    {
      name: "my-cowork-sessions",
      version: 2,
      migrate: (persisted, version) => {
        const state = (persisted || {}) as {
          sessions?: Record<string, unknown>[];
          activeId?: string | null;
          messagesById?: Record<string, Message[]>;
        };
        const sessions = (state.sessions || []).map((raw) =>
          migrateProject(raw as Record<string, unknown>),
        );
        return {
          sessions,
          activeId: state.activeId ?? null,
          messagesById: state.messagesById || {},
        };
      },
      onRehydrateStorage: () => (state) => {
        const id = state?.activeId ?? null;
        if (id) restoreProject(id, state?.messagesById?.[id] ?? []);
        else setActiveProjectRuntime(null);
        setLiveBoundId(id);
      },
    },
  ),
);

setProjectMessagePersist((id, messages) => {
  useSessionsStore.getState().saveMessages(id, messages);
});

export function ensureActiveSession(): string {
  const s = useSessionsStore.getState();
  if (s.activeId && s.sessions.some((x) => x.id === s.activeId)) {
    if (liveBoundId !== s.activeId) hydrateLiveChat();
    return s.activeId;
  }
  const spaceId = useSpacesStore.getState().activeSpaceId || DEFAULT_SPACE_ID;
  const inSpace = s.sessions.find((x) => x.spaceId === spaceId);
  if (inSpace) {
    s.setActive(inSpace.id);
    return inSpace.id;
  }
  if (s.sessions[0]) {
    s.setActive(s.sessions[0].id);
    return s.sessions[0].id;
  }
  return s.createProject();
}

export function getActiveProjectContext(): {
  project: Project | null;
  space: CoworkSpace | null;
} {
  const sessions = useSessionsStore.getState();
  const spaces = useSpacesStore.getState();
  const project =
    sessions.sessions.find((x) => x.id === sessions.activeId) ?? null;
  const spaceId = project?.spaceId || spaces.activeSpaceId;
  const space = spaces.spaces.find((x) => x.id === spaceId) ?? null;
  return { project, space };
}

/** Delete a Space and all Projects under it. Keeps at least one Space. */
export function deleteSpaceCompletely(spaceId: string): boolean {
  if (useSpacesStore.getState().spaces.length <= 1) return false;
  useSessionsStore.getState().deleteProjectsInSpace(spaceId);
  useSpacesStore.getState().deleteSpace(spaceId);
  if (!useSessionsStore.getState().activeId) {
    ensureActiveSession();
  } else {
    const active = useSessionsStore
      .getState()
      .sessions.find((x) => x.id === useSessionsStore.getState().activeId);
    if (active) {
      useSpacesStore.getState().setActiveSpace(active.spaceId);
    }
  }
  return !useSpacesStore.getState().spaces.some((s) => s.id === spaceId);
}
