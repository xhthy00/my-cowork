/**
 * Adapted from eigent: src/store/pageTabStore.ts (layout + preview + hub).
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";
import { leaveIndustryPage } from "./industryNavigation";

import type { SessionPreviewTab } from "./preview";

export type HubTab = "home" | "workbench" | "agents" | "knowledge" | "connectors" | "browser" | "settings";
export type HomeSection = "spaces" | "projects" | "triggers";
export type WorkspaceView = "workspace" | "hub";
export type AgentsSection = "skills" | "sub-agents" | "memory";
export type BrowserSection = "agent" | "cdp" | "extension" | "cookies";

export function migratePageTabState(persisted: unknown): unknown {
  const state = persisted as Omit<Partial<PageTabState>, "agentsSection"> & { agentsSection?: string };
  if (state?.agentsSection === "models") {
    return { ...state, agentsSection: "skills" };
  }
  if (state?.browserSection === "cdp") {
    return { ...state, browserSection: "agent" };
  }
  return persisted;
}

interface PageTabState {
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
      workspaceView: "hub",
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
      version: 2,
      migrate: (persisted) => migratePageTabState(persisted),
      partialize: (s) => ({
        projectSidebarFolded: s.projectSidebarFolded,
        projectHistoryCollapsed: s.projectHistoryCollapsed,
        hubTab: s.hubTab,
        agentsSection: s.agentsSection,
        browserSection: s.browserSection,
      }),
    },
  ),
);

export type { SessionPreviewTab };
