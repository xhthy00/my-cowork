/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";

import { migratePageTabState, usePageTabStore } from "../../renderer/src/store/pageTab";

describe("pageTab Eigent UE rules", () => {
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
    usePageTabStore.getState().setHubTab("browser");
    const s = usePageTabStore.getState();
    expect(s.workspaceView).toBe("hub");
    expect(s.hubTab).toBe("browser");
  });

  it("setHubTab can open the knowledge tab", () => {
    usePageTabStore.setState({ workspaceView: "workspace", hubTab: "home" });
    usePageTabStore.getState().setHubTab("knowledge");
    const s = usePageTabStore.getState();
    expect(s.workspaceView).toBe("hub");
    expect(s.hubTab).toBe("knowledge");
  });

  it("treats a persisted models agentsSection as skills", () => {
    expect(
      migratePageTabState({ agentsSection: "models", hubTab: "agents" }),
    ).toMatchObject({ agentsSection: "skills", hubTab: "agents" });
  });
});
