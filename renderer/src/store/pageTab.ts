/**
 * Adapted from eigent: src/store/pageTabStore.ts (layout + preview + hub).
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";
import { leaveIndustryPage } from "./industryNavigation";

import type { SessionPreviewTab } from "./preview";

export type HubTab = "home" | "workbench" | "agents" | "knowledge" | "connectors" | "browser" | "settings";
export type SettingsSection = "general" | "appearance" | "schedule" | "model" | "knowledge" | "browser" | "paths" | "channels" | "search" | "audit" | "about";
export type HomeSection = "spaces" | "projects" | "triggers";
export type WorkspaceView = "workspace" | "hub";
export type AgentsSection = "skills" | "skill-store" | "sub-agents" | "memory";
export type BrowserSection = "agent" | "cdp" | "extension" | "cookies";

export function migratePageTabState(persisted: unknown, version = 0): unknown {
  const state = persisted as Partial<Omit<PageTabState, "agentsSection">> & { agentsSection?: string };
  if (!state || typeof state !== "object") return persisted;
  return {
    ...state,
    ...(state.agentsSection === "models" ? { agentsSection: "skills" } : {}),
    ...(version < 2 && state.browserSection === "cdp" ? { browserSection: "agent" } : {}),
    ...(["settings", "knowledge", "browser"].includes(state.hubTab || "") ? { hubTab: "home" } : {}),
  };
}

interface PageTabState {
  settingsOpen: boolean;
  settingsSection: SettingsSection;
  openSettings: (section?: SettingsSection) => void;
  setSettingsOpen: (open: boolean) => void;
  workspaceView: WorkspaceView;
  hubTab: HubTab;
  homeSection: HomeSection;
  agentsSection: AgentsSection;
  browserSection: BrowserSection;
  projectSidebarFolded: boolean;
  projectHistoryCollapsed: boolean;
  sidePanelVisible: boolean;
  previewOpen: boolean;
  setWorkspaceView: (v: WorkspaceView) => void;
  setHubTab: (t: HubTab) => void;
  setHomeSection: (s: HomeSection) => void;
  setAgentsSection: (s: AgentsSection) => void;
  setBrowserSection: (s: BrowserSection) => void;
  toggleProjectSidebar: () => void;
  setProjectHistoryCollapsed: (collapsed: boolean) => void;
  setSidePanelVisible: (v: boolean) => void;
  setPreviewOpen: (v: boolean) => void;
  /** Eigent UE: opening preview folds side panel. */
  openPreviewFoldSide: () => void;
}

export const usePageTabStore = create<PageTabState>()(
  persist(
    (set, get) => ({
      settingsOpen: false,
      settingsSection: "general",
      openSettings: (settingsSection = "general") => set({ settingsOpen: true, settingsSection }),
      setSettingsOpen: (settingsOpen) => set({ settingsOpen }),
      workspaceView: "workspace",
      hubTab: "home",
      homeSection: "spaces",
      agentsSection: "skills",
      browserSection: "agent",
      projectSidebarFolded: false,
      projectHistoryCollapsed: false,
      sidePanelVisible: true,
      previewOpen: false,
      setWorkspaceView: (workspaceView) => {
        if (get().workspaceView === "hub" && get().hubTab === "workbench" && workspaceView !== "hub" && !leaveIndustryPage()) return;
        set({ workspaceView });
      },
      setHubTab: (hubTab) => {
        if (hubTab === "settings") { get().openSettings(); return; }
        if (hubTab === "knowledge" || hubTab === "browser") { get().openSettings(hubTab); return; }
        if (get().workspaceView === "hub" && get().hubTab === "workbench" && hubTab !== "workbench" && !leaveIndustryPage()) return;
        set({ hubTab, workspaceView: "hub" });
      },
      setHomeSection: (homeSection) => set({ homeSection }),
      setAgentsSection: (agentsSection) => set({ agentsSection }),
      setBrowserSection: (browserSection) => set({ browserSection }),
      toggleProjectSidebar: () =>
        set((s) => ({ projectSidebarFolded: !s.projectSidebarFolded })),
      setProjectHistoryCollapsed: (projectHistoryCollapsed) =>
        set({ projectHistoryCollapsed }),
      setSidePanelVisible: (sidePanelVisible) => set({ sidePanelVisible }),
      setPreviewOpen: (previewOpen) => set({ previewOpen }),
      openPreviewFoldSide: () =>
        set({ previewOpen: true, sidePanelVisible: false }),
    }),
    {
      name: "my-cowork-page-tab",
      version: 3,
      migrate: (persisted, version) => migratePageTabState(persisted, version),
      partialize: (s) => ({
        projectSidebarFolded: s.projectSidebarFolded,
        projectHistoryCollapsed: s.projectHistoryCollapsed,
        hubTab: ["settings", "knowledge", "browser"].includes(s.hubTab) ? "home" : s.hubTab,
        agentsSection: s.agentsSection,
        browserSection: s.browserSection,
      }),
    },
  ),
);

export type { SessionPreviewTab };
