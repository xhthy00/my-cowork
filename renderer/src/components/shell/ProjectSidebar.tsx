import { useAppVersion } from "@/hooks/useAppVersion";
import { useCompactLayout } from "@/hooks/useCompactLayout";
/**
 * Main navigation and conversation history for the active workspace.
 */
import {
  Blocks,
  FolderKanban,
  Settings,
  MessageSquarePlus,
  Sparkles,
  ChevronDown,
  Trash2,
  Zap,
} from "lucide-react";
import appLogo from "@/assets/brand/app-logo.png";
import { useMemo, useState } from "react";

import AlertDialog from "@/components/ui/alertDialog";
import TopBar from "@/components/shell/TopBar";
import { cn } from "@/lib/utils";
import {
  PROJECT_SIDEBAR_EXPANDED_WIDTH_PX,
  PROJECT_SIDEBAR_RAIL_WIDTH_PX,
} from "@/components/session/sessionSidePanelLayout";
import { usePageTabStore } from "@/store/pageTab";
import {
  ensureActiveSession,
  useSessionsStore,
} from "@/store/sessions";
import { useSpacesStore } from "@/store/spaces";

function historyGroup(timestamp: number, today: Date): string {
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
  if (timestamp >= start) return "今天";
  if (timestamp >= start - 86_400_000) return "昨天";
  if (timestamp >= start - 7 * 86_400_000) return "近 7 天";
  return "更早";
}

function historyTime(timestamp: number, today: Date): string {
  const date = new Date(timestamp);
  if (!Number.isFinite(date.getTime())) return "";
  return ["今天", "昨天"].includes(historyGroup(timestamp, today))
    ? new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit" }).format(date)
    : new Intl.DateTimeFormat("zh-CN", {
        month: "numeric",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }).format(date);
}

function navTabClass(active: boolean) {
  return cn(
    "h-8 w-full min-w-0 shrink-0 rounded-xl flex items-center justify-start gap-3 px-3 text-left outline-none overflow-hidden transition-colors duration-200",
    "text-ds-text-neutral-muted-default text-body-sm font-medium",
    "hover:bg-ds-bg-neutral-subtle-default",
    active && "bg-ds-bg-neutral-subtle-default",
  );
}

export default function ProjectSidebar({
  fill = false,
}: {
  /** When true, fill parent (resizable panel); otherwise fixed Eigent rail/expanded width. */
  fill?: boolean;
}) {
  const version = useAppVersion();
  const hubTab = usePageTabStore((s) => s.hubTab);
  const homeSection = usePageTabStore((s) => s.homeSection);
  const sidebarFolded = usePageTabStore((s) => s.projectSidebarFolded);
  const compact = useCompactLayout();
  const folded = sidebarFolded || compact;
  const historyCollapsed = usePageTabStore((s) => s.projectHistoryCollapsed);
  const setHistoryCollapsed = usePageTabStore((s) => s.setProjectHistoryCollapsed);
  const workspaceView = usePageTabStore((s) => s.workspaceView);
  const setWorkspaceView = usePageTabStore((s) => s.setWorkspaceView);
  const setHubTab = usePageTabStore((s) => s.setHubTab);
  const sessions = useSessionsStore((s) => s.sessions);
  const activeId = useSessionsStore((s) => s.activeId);
  const setActive = useSessionsStore((s) => s.setActive);
  const createProject = useSessionsStore((s) => s.createProject);
  const deleteSession = useSessionsStore((s) => s.deleteSession);
  const spaces = useSpacesStore((s) => s.spaces);
  const activeSpaceId = useSpacesStore((s) => s.activeSpaceId);
  const [deleteId, setDeleteId] = useState<string | null>(null);

  const deleteTarget = deleteId
    ? sessions.find((s) => s.id === deleteId)
    : null;

  const width = folded
    ? PROJECT_SIDEBAR_RAIL_WIDTH_PX
    : PROJECT_SIDEBAR_EXPANDED_WIDTH_PX;

  const activeSpace = spaces.find((s) => s.id === activeSpaceId) ?? spaces[0];
  const projects = useMemo(
    () => sessions.filter((s) => s.spaceId === (activeSpaceId || activeSpace?.id)),
    [sessions, activeSpaceId, activeSpace?.id],
  );
  const historyGroups = useMemo(() => {
    const today = new Date();
    const groups: Array<{ label: string; projects: typeof projects }> = [];
    for (const project of [...projects].sort((a, b) => b.updatedAt - a.updatedAt)) {
      const label = historyGroup(project.updatedAt, today);
      const group = groups.find((item) => item.label === label);
      if (group) group.projects.push(project);
      else groups.push({ label, projects: [project] });
    }
    return { groups, today };
  }, [projects]);

  function enterWorkspace() {
    setWorkspaceView("workspace");
    return usePageTabStore.getState().workspaceView === "workspace";
  }

  function startNewTask() {
    if (!enterWorkspace()) return;
    createProject();
    setHistoryCollapsed(false);
  }

  return (
    <aside
      className="project-sidebar box-border flex h-full min-h-0 min-w-0 shrink-0 flex-col overflow-hidden rounded-2xl bg-ds-bg-neutral-default-default p-1"
      data-folded={folded}
      style={fill ? { width: "100%" } : { width }}
    >
      <div className="flex h-full min-h-0 w-full min-w-0 flex-col overflow-hidden">
        <div className="sidebar-header">
          <div className="sidebar-brand">
            {folded ? <img src={appLogo} alt="MyCowork" /> : <><span>MyCoWork</span><small>v{version}</small></>}
          </div>
          <TopBar />
        </div>
        <nav aria-label="主要导航" className="sidebar-navigation flex w-full shrink-0 flex-col gap-1">
          {[
            { label: "新建任务", icon: MessageSquarePlus, active: workspaceView === "workspace", action: startNewTask },
            { label: "项目", icon: FolderKanban, active: workspaceView === "hub" && hubTab === "home" && homeSection !== "triggers", action: () => { setHubTab("home"); usePageTabStore.getState().setHomeSection("projects"); } },
            { label: "助理 · 技能 · 连接器", icon: Sparkles, active: workspaceView === "hub" && (hubTab === "connectors" || hubTab === "agents"), action: () => setHubTab("agents") },
            { label: "自动化", icon: Zap, active: workspaceView === "hub" && hubTab === "home" && homeSection === "triggers", action: () => { setHubTab("home"); usePageTabStore.getState().setHomeSection("triggers"); } },
            { label: "工作台", icon: Blocks, active: workspaceView === "hub" && hubTab === "workbench", action: () => setHubTab("workbench") },
          ].map(({ label, icon: Icon, active, action }) => <button key={label} type="button" title={label} aria-label={label} aria-current={active ? "page" : undefined} data-active={active} className={cn(navTabClass(active), folded && "justify-center px-0 gap-0")} onClick={action}><Icon className="h-5 w-5 shrink-0" aria-hidden="true" />{!folded && <span className="truncate">{label}</span>}</button>)}
        </nav>
        <div className="my-2 px-3">
          <div className="h-px w-full bg-ds-border-neutral-default-default" />
        </div>

        {!folded && (
          <>
            <button
              type="button"
              aria-label={historyCollapsed ? "展开历史会话" : "收起历史会话"}
              aria-expanded={!historyCollapsed}
              aria-controls="project-history-list"
              className="mb-1 flex h-9 w-full shrink-0 items-center justify-between rounded-lg px-3 text-left text-xs font-semibold tracking-wide text-ds-text-neutral-muted-default transition-colors hover:bg-ds-bg-neutral-subtle-default focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ds-ring-neutral-subtle-default"
              onClick={() => setHistoryCollapsed(!historyCollapsed)}
            >
              <span>任务</span>
              <span className="flex items-center gap-1.5">
                <span className="tabular-nums">{projects.length}</span>
                <ChevronDown
                  aria-hidden="true"
                  className={cn("h-3.5 w-3.5 transition-transform", historyCollapsed && "-rotate-90")}
                />
              </span>
            </button>
            <div
              id="project-history-list"
              hidden={historyCollapsed}
              className={cn(
                "scrollbar-hide min-h-0 min-w-0 flex-1 space-y-0.5 overflow-y-auto overflow-x-hidden px-0.5",
                historyCollapsed && "hidden",
              )}
            >
              {historyGroups.groups.flatMap((group) => [
                <div key={`group-${group.label}`} className="px-3 pb-1 pt-3 text-xs font-semibold text-ds-text-neutral-muted-default first:pt-1">
                  {group.label}
                </div>,
                ...group.projects.map((s) => (
                <div
                  key={s.id}
                  data-active={activeId === s.id}
                  className={cn(
                    "project-row group/project relative flex w-full items-center gap-1 rounded-xl pr-1 transition-colors",
                    activeId === s.id
                      ? "bg-ds-bg-neutral-subtle-default text-ds-text-neutral-default-default"
                      : "text-ds-text-neutral-muted-default hover:bg-ds-bg-neutral-subtle-default",
                  )}
                >
                  <button
                    type="button"
                    title={`${s.title} · ${new Date(s.updatedAt).toLocaleString("zh-CN")}`}
                    className="flex min-w-0 flex-1 items-center gap-2 rounded-xl px-3 py-2 text-left text-body-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ds-ring-neutral-subtle-default"
                    onClick={() => {
                      if (!enterWorkspace()) return;
                      setActive(s.id);
                      setWorkspaceView("workspace");
                    }}
                  >
                    {s.status === "done" ? (
                      <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-ds-icon-status-completed-default text-[10px] text-white">
                        ✓
                      </span>
                    ) : (
                      <span className="h-4 w-4 shrink-0 rounded-full border border-ds-border-neutral-default-default" />
                    )}
                    <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                      <span className="truncate font-medium">{s.title}</span>
                      <span className="text-xs leading-4 text-ds-text-neutral-muted-default">
                        {historyTime(s.updatedAt, historyGroups.today)}
                        {s.status === "running" ? " · 进行中" : s.status === "error" ? " · 未完成" : ""}
                      </span>
                    </span>
                  </button>
                  <button
                    type="button"
                    title="删除项目"
                    aria-label={`删除 ${s.title}`}
                    className="mr-1 hidden h-7 w-7 shrink-0 items-center justify-center rounded-lg text-ds-text-neutral-subtle-default hover:bg-ds-bg-neutral-strong-default hover:text-ds-text-error-default-default group-hover/project:flex"
                    onClick={(e) => {
                      e.stopPropagation();
                      setDeleteId(s.id);
                    }}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))])}
              {projects.length === 0 && (
                <p className="px-3 py-2 text-xs text-ds-text-neutral-subtle-default">
                  暂无项目
                </p>
              )}
            </div>
          </>
        )}
      </div>

      <button type="button" data-settings-trigger className="sidebar-settings-icon" aria-label="设置" title="设置" onClick={() => usePageTabStore.getState().openSettings()}>
        <Settings aria-hidden="true" size={20} />
      </button>

      <AlertDialog
        open={deleteId != null}
        title="删除项目"
        description={
          deleteTarget
            ? `确定删除「${deleteTarget.title}」？对话记录将一并清除，此操作不可撤销。`
            : "确定删除该项目？此操作不可撤销。"
        }
        confirmLabel="删除"
        confirmVariant="destructive"
        onCancel={() => setDeleteId(null)}
        onConfirm={() => {
          if (!deleteId) return;
          const id = deleteId;
          setDeleteId(null);
          deleteSession(id);
          if (!useSessionsStore.getState().activeId) {
            ensureActiveSession();
          }
        }}
      />

    </aside>
  );
}
