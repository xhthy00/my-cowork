/**
 * Adapted from eigent: src/store/pageTabStore.ts (layout + preview + hub).
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { SessionPreviewTab } from "./preview";

export type HubTab = "home" | "agents" | "connectors" | "browser" | "settings";
export type HomeSection = "spaces" | "projects" | "triggers";
export type WorkspaceView = "workspace" | "hub";
export type AgentsSection = "models" | "skills" | "sub-agents" | "memory";
export type BrowserSection = "cdp" | "extension" | "cookies";

interface PageTabState {
  workspaceView: WorkspaceView;
  hubTab: HubTab;
  homeSection: HomeSection;
  agentsSection: AgentsSection;
  browserSection: BrowserSection;
  projectSidebarFolded: boolean;
  sidePanelVisible: boolean;
  previewOpen: boolean;
  setWorkspaceView: (v: WorkspaceView) => void;
  setHubTab: (t: HubTab) => void;
  setHomeSection: (s: HomeSection) => void;
  setAgentsSection: (s: AgentsSection) => void;
  setBrowserSection: (s: BrowserSection) => void;
  toggleProjectSidebar: () => void;
  setSidePanelVisible: (v: boolean) => void;
  setPreviewOpen: (v: boolean) => void;
  /** Eigent UE: opening preview folds side panel. */
  openPreviewFoldSide: () => void;
}

export const usePageTabStore = create<PageTabState>()(
  persist(
    (set) => ({
      workspaceView: "hub",
      hubTab: "home",
      homeSection: "spaces",
      agentsSection: "skills",
      browserSection: "cdp",
      projectSidebarFolded: false,
      sidePanelVisible: true,
      previewOpen: false,
      setWorkspaceView: (workspaceView) => set({ workspaceView }),
      setHubTab: (hubTab) => set({ hubTab, workspaceView: "hub" }),
      setHomeSection: (homeSection) => set({ homeSection }),
      setAgentsSection: (agentsSection) => set({ agentsSection }),
      setBrowserSection: (browserSection) => set({ browserSection }),
      toggleProjectSidebar: () =>
        set((s) => ({ projectSidebarFolded: !s.projectSidebarFolded })),
      setSidePanelVisible: (sidePanelVisible) => set({ sidePanelVisible }),
      setPreviewOpen: (previewOpen) => set({ previewOpen }),
      openPreviewFoldSide: () =>
        set({ previewOpen: true, sidePanelVisible: false }),
    }),
    {
      name: "my-cowork-page-tab",
      partialize: (s) => ({
        projectSidebarFolded: s.projectSidebarFolded,
        hubTab: s.hubTab,
        agentsSection: s.agentsSection,
        browserSection: s.browserSection,
      }),
    },
  ),
);

export type { SessionPreviewTab };
