/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";

import { migratePageTabState, usePageTabStore } from "../../renderer/src/store/pageTab";

describe("pageTab Eigent UE rules", () => {
  it("opens settings over the current workbench without navigating away", () => {
    usePageTabStore.setState({ workspaceView: "hub", hubTab: "workbench", settingsOpen: false });
    usePageTabStore.getState().setHubTab("settings");
    expect(usePageTabStore.getState()).toMatchObject({ workspaceView: "hub", hubTab: "workbench", settingsOpen: true, settingsSection: "general" });
    usePageTabStore.getState().setSettingsOpen(false);
  });
  it("openPreviewFoldSide folds side panel and opens preview", () => {
    usePageTabStore.setState({
      previewOpen: false,
      sidePanelVisible: true,
    });
    usePageTabStore.getState().openPreviewFoldSide();
    const s = usePageTabStore.getState();
    expect(s.previewOpen).toBe(true);
    expect(s.sidePanelVisible).toBe(false);
  });

  it("setHubTab switches workspace to hub", () => {
    usePageTabStore.setState({ workspaceView: "workspace", hubTab: "home" });
    usePageTabStore.getState().setHubTab("agents");
    const s = usePageTabStore.getState();
    expect(s.workspaceView).toBe("hub");
    expect(s.hubTab).toBe("agents");
  });

  it.each(["knowledge", "browser"] as const)("opens legacy %s links in settings while keeping the current page", (section) => {
    usePageTabStore.setState({ workspaceView: "workspace", hubTab: "agents", settingsOpen: false });
    usePageTabStore.getState().setHubTab(section);
    expect(usePageTabStore.getState()).toMatchObject({ workspaceView: "workspace", hubTab: "agents", settingsOpen: true, settingsSection: section });
    usePageTabStore.getState().setSettingsOpen(false);
  });

  it("treats a persisted models agentsSection as skills", () => {
    expect(
      migratePageTabState({ agentsSection: "models", hubTab: "agents" }),
    ).toMatchObject({ agentsSection: "skills", hubTab: "agents" });
  });

  it("migrates removed hub pages without resetting an existing CDP preference", () => {
    expect(migratePageTabState({ hubTab: "browser", browserSection: "cdp", agentsSection: "skill-store" }, 2))
      .toMatchObject({ hubTab: "home", browserSection: "cdp", agentsSection: "skill-store" });
  });
});
