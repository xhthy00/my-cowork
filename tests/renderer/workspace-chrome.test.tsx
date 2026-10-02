/** @vitest-environment jsdom */
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import WorkspaceShell from "../../renderer/src/components/workspace/WorkspaceShell";
import PreviewPanel from "../../renderer/src/components/preview/PreviewPanel";
import { usePageTabStore } from "../../renderer/src/store/pageTab";
import { usePreviewStore } from "../../renderer/src/store/preview";

vi.mock("react-resizable-panels", () => ({
  Group: ({ children }: any) => <div>{children}</div>,
  Panel: ({ children }: any) => <div>{children}</div>,
  Separator: () => <div role="separator" />,
}));
vi.mock("../../renderer/src/components/preview/PreviewBrowserLayer", () => ({
  default: () => null, getPreviewWebview: () => null,
}));
vi.mock("../../renderer/src/components/preview/PreviewTerminal", () => ({ default: () => null }));

describe("workspace chrome alignment", () => {
  let width = 313.25;
  let sidebarResize: (() => void) | undefined;
  beforeEach(() => {
    usePageTabStore.setState({ projectSidebarFolded: false, previewOpen: true, sidePanelVisible: false });
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function () {
      return { width: this.classList.contains("shell-sidebar-column") ? width : 0 } as DOMRect;
    });
    vi.stubGlobal("ResizeObserver", class {
      constructor(private notify: () => void) {}
      observe(target: Element) { if (target.classList.contains("shell-sidebar-column")) sidebarResize = this.notify; }
      unobserve() {}
      disconnect() {}
    });
  });
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  it("matches chrome to the measured sidebar edge after resizing", () => {
    render(<WorkspaceShell sidebar={<div>导航</div>} main={<div>内容</div>} />);
    expect(document.documentElement.style.getPropertyValue("--shell-sidebar-width")).toBe("313.25px");
    width = 287.5;
    sidebarResize?.();
    expect(document.documentElement.style.getPropertyValue("--shell-sidebar-width")).toBe("287.5px");
  });

  it("opens run details without closing the active preview tab", () => {
    usePreviewStore.setState({open:true, tabs:[{id:"chooser", type:"chooser", title:"新视图"}],activeTabId:"chooser"});
    render(<PreviewPanel />);
    fireEvent.click(screen.getByRole("button", {name:"展开运行详情"}));
    expect(usePageTabStore.getState().sidePanelVisible).toBe(true);
    expect(usePreviewStore.getState()).toMatchObject({open:true,activeTabId:"chooser"});
    fireEvent.click(screen.getByRole("button", {name:"收起运行详情"}));
    expect(usePageTabStore.getState().sidePanelVisible).toBe(false);
    expect(usePreviewStore.getState().tabs).toHaveLength(1);
  });
});
