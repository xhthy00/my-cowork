/**
 * Adapted from eigent Workspace shell: ProjectSidebar ↔ main drag resize
 * via react-resizable-panels v4 Group/Panel/Separator.
 *
 * The sidebar width is user-draggable within generous bounds and persisted
 * across restarts (stored as the Group layout in localStorage).
 */
import { useCallback } from "react";
import {
  Group,
  Panel,
  Separator,
  type Layout,
} from "react-resizable-panels";

import { cn } from "@/lib/utils";
import {
  PROJECT_SIDEBAR_EXPANDED_WIDTH_PX,
  PROJECT_SIDEBAR_RAIL_WIDTH_PX,
} from "@/components/session/sessionSidePanelLayout";
import { usePageTabStore } from "@/store/pageTab";

const SIDEBAR_LAYOUT_KEY = "my-cowork-workspace-shell-layout";

/** Sidebar stays usable between these bounds but is no longer capped at 360px. */
const SIDEBAR_MIN_WIDTH_PX = 160;
/** Cap relative to the window so wide screens can allocate more room. */
const SIDEBAR_MAX_WIDTH = "55vw";
/** Keep the main workspace always usable. */
const MAIN_MIN_WIDTH_PX = 360;

function loadPersistedLayout(): Layout | undefined {
  try {
    const raw = window.localStorage.getItem(SIDEBAR_LAYOUT_KEY);
    if (!raw) return undefined;
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    if (
      parsed &&
      typeof parsed === "object" &&
      typeof parsed.sidebar === "number" &&
      parsed.sidebar > 0 &&
      typeof parsed.main === "number" &&
      parsed.main > 0
    ) {
      return { sidebar: parsed.sidebar, main: parsed.main };
    }
  } catch {
    // Corrupt storage — fall back to defaults.
  }
  return undefined;
}

export default function WorkspaceShell({
  sidebar,
  main,
}: {
  sidebar: React.ReactNode;
  main: React.ReactNode;
}) {
  const folded = usePageTabStore((s) => s.projectSidebarFolded);

  const persistLayout = useCallback(
    (layout: Layout, meta: { isUserInteraction: boolean }) => {
      if (!meta.isUserInteraction) return;
      try {
        window.localStorage.setItem(SIDEBAR_LAYOUT_KEY, JSON.stringify(layout));
      } catch {
        // Storage unavailable — layout just won't persist.
      }
    },
    [],
  );

  if (folded) {
    return (
      <div className="flex h-full min-h-0 w-full min-w-0 flex-1 flex-row overflow-hidden">
        <div
          className="box-border mr-1 flex h-full shrink-0 flex-col overflow-hidden"
          style={{ width: PROJECT_SIDEBAR_RAIL_WIDTH_PX }}
        >
          {sidebar}
        </div>
        <div className="workspace flex min-h-0 min-w-0 flex-1 overflow-hidden rounded-2xl bg-ds-bg-neutral-subtle-default">
          {main}
        </div>
      </div>
    );
  }

  return (
    <Group
      id="workspace-shell"
      orientation="horizontal"
      className="h-full min-h-0 w-full min-w-0 flex-1"
      defaultLayout={loadPersistedLayout()}
      onLayoutChanged={persistLayout}
      resizeTargetMinimumSize={{ coarse: 32, fine: 12 }}
    >
      <Panel
        id="sidebar"
        defaultSize={PROJECT_SIDEBAR_EXPANDED_WIDTH_PX}
        minSize={SIDEBAR_MIN_WIDTH_PX}
        maxSize={SIDEBAR_MAX_WIDTH}
        groupResizeBehavior="preserve-pixel-size"
        className="min-h-0 min-w-0"
      >
        <div className="box-border mr-1 flex h-full min-h-0 w-full flex-col overflow-hidden">
          {sidebar}
        </div>
      </Panel>
      <Separator
        className={cn(
          "relative z-10 w-[2px] shrink-0 cursor-col-resize bg-transparent transition-colors",
          "hover:bg-ds-bg-brand-subtle-default",
          // Widen the invisible hit area so the handle is easy to grab.
          "before:absolute before:inset-y-0 before:-left-1.5 before:-right-1.5 before:content-['']",
          "after:absolute after:inset-y-0 after:left-1/2 after:w-1 after:-translate-x-1/2 after:bg-ds-bg-neutral-default-default after:transition-colors",
          "data-[separator-state=active]:after:bg-ds-bg-brand-default-focus",
        )}
      />
      <Panel id="main" minSize={MAIN_MIN_WIDTH_PX} className="min-h-0 min-w-0">
        <div className="workspace flex h-full min-h-0 min-w-0 overflow-hidden rounded-2xl bg-ds-bg-neutral-subtle-default">
          {main}
        </div>
      </Panel>
    </Group>
  );
}
