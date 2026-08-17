/**
 * Adapted from eigent: pages/Home (toolbar + Spaces/Projects/Tasks/Triggers).
 * Spaces/Projects are local; Triggers remain a stub.
 */
import {
  ArrowUpDown,
  CheckCircle2,
  Folder,
  FolderPlus,
  LayoutGrid,
  List,
  Loader2,
  MoreHorizontal,
  Pencil,
  Plus,
  PlusCircle,
  Trash2,
  Zap,
} from "lucide-react";
import { useMemo, useState } from "react";

import SearchInput from "@/components/hub/SearchInput";
import AlertDialog from "@/components/ui/alertDialog";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import { usePageTabStore, type HomeSection } from "@/store/pageTab";
import {
  ensureActiveSession,
  deleteSpaceCompletely,
  useSessionsStore,
  type ChatSession,
} from "@/store/sessions";
import { useSpacesStore, type CoworkSpace } from "@/store/spaces";

const homeHubSurfaceClass =
  "cursor-pointer rounded-xl border border-transparent bg-ds-bg-neutral-default-default px-6 py-4 text-left shadow-sm transition-colors duration-200 hover:border-ds-border-neutral-subtle-default hover:bg-ds-bg-neutral-subtle-default";

function formatAgo(ts: number): string {
  const sec = Math.max(0, Math.floor((Date.now() - ts) / 1000));
  if (sec < 60) return "刚刚";
  if (sec < 3600) return `${Math.floor(sec / 60)} 分钟前`;
  if (sec < 86400) return `${Math.floor(sec / 3600)} 小时前`;
  return `${Math.floor(sec / 86400)} 天前`;
}

function statusIcon(status: ChatSession["status"]) {
  if (status === "running") {
    return <Loader2 className="h-4 w-4 animate-spin text-ds-text-neutral-muted-default" />;
  }
  if (status === "done") {
    return <CheckCircle2 className="h-4 w-4 text-ds-icon-status-completed-default" />;
  }
  if (status === "error") {
    return <span className="h-2 w-2 rounded-full bg-[var(--danger)]" />;
  }
  return <span className="h-2 w-2 rounded-full bg-ds-border-neutral-default-default" />;
}

function SessionCard({
  session,
  onRequestDelete,
}: {
  session: ChatSession;
  onRequestDelete: (id: string) => void;
}) {
  const setActive = useSessionsStore((s) => s.setActive);
  const setWorkspaceView = usePageTabStore((s) => s.setWorkspaceView);

  return (
    <div className={cn(homeHubSurfaceClass, "group/card relative")}>
      <button
        type="button"
        className="w-full text-left"
        onClick={() => {
          setActive(session.id);
          setWorkspaceView("workspace");
        }}
      >
        <div className="flex items-start gap-3">
          <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-ds-bg-neutral-subtle-default text-ds-icon-neutral-muted-default">
            <Folder className="h-4 w-4" />
          </div>
          <div className="min-w-0 flex-1 pr-8">
            <div className="flex items-center gap-2">
              <span className="truncate text-[14px] font-semibold text-ds-text-neutral-default-default">
                {session.title}
              </span>
              {statusIcon(session.status)}
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-[12px] text-ds-text-neutral-subtle-default">
              <span className="rounded-md bg-ds-bg-neutral-subtle-default px-1.5 py-0.5">
                {{
                  idle: "空闲",
                  running: "运行中",
                  done: "已完成",
                  error: "失败",
                }[session.status] || session.status}
              </span>
              <span>{formatAgo(session.updatedAt)}</span>
            </div>
          </div>
        </div>
      </button>
      <button
        type="button"
        title="删除"
        aria-label={`删除 ${session.title}`}
        className="absolute right-3 top-3 flex h-8 w-8 items-center justify-center rounded-lg text-ds-text-neutral-subtle-default opacity-0 transition-opacity hover:bg-ds-bg-neutral-subtle-default hover:text-ds-text-error-default-default group-hover/card:opacity-100"
        onClick={(e) => {
          e.stopPropagation();
          onRequestDelete(session.id);
        }}
      >
        <Trash2 className="h-4 w-4" />
      </button>
    </div>
  );
}

type ViewMode = "grid" | "list";
type SortBy = "updated" | "created" | "name";

export default function HomeHub() {
  const homeSection = usePageTabStore((s) => s.homeSection);
  const setHomeSection = usePageTabStore((s) => s.setHomeSection);
  const setWorkspaceView = usePageTabStore((s) => s.setWorkspaceView);
  const sessions = useSessionsStore((s) => s.sessions);
  const createSession = useSessionsStore((s) => s.createSession);
  const createProject = useSessionsStore((s) => s.createProject);
  const deleteSession = useSessionsStore((s) => s.deleteSession);
  const spaces = useSpacesStore((s) => s.spaces);
  const activeSpaceId = useSpacesStore((s) => s.activeSpaceId);
  const setActiveSpace = useSpacesStore((s) => s.setActiveSpace);
  const createBlankSpace = useSpacesStore((s) => s.createBlankSpace);
  const createFolderSpace = useSpacesStore((s) => s.createFolderSpace);
  const renameSpace = useSpacesStore((s) => s.renameSpace);
  const [query, setQuery] = useState("");
  const [viewMode, setViewMode] = useState<ViewMode>("grid");
  const [sortBy, setSortBy] = useState<SortBy>("updated");
  const [sortDesc, setSortDesc] = useState(true);
  const [sortMenuOpen, setSortMenuOpen] = useState(false);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [deleteSpaceId, setDeleteSpaceId] = useState<string | null>(null);
  const [renameSpaceTarget, setRenameSpaceTarget] = useState<CoworkSpace | null>(
    null,
  );
  const [renameValue, setRenameValue] = useState("");

  const deleteTarget = deleteId
    ? sessions.find((s) => s.id === deleteId)
    : null;
  const deleteSpaceTarget = deleteSpaceId
    ? spaces.find((s) => s.id === deleteSpaceId)
    : null;
  const canDeleteSpace = spaces.length > 1;

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    let list =
      homeSection === "projects"
        ? sessions.filter((s) => !activeSpaceId || s.spaceId === activeSpaceId)
        : sessions;
    if (q) list = list.filter((s) => s.title.toLowerCase().includes(q));
    list = [...list].sort((a, b) => {
      let cmp = 0;
      if (sortBy === "name") cmp = a.title.localeCompare(b.title, "zh");
      else if (sortBy === "created") cmp = a.createdAt - b.createdAt;
      else cmp = a.updatedAt - b.updatedAt;
      return sortDesc ? -cmp : cmp;
    });
    return list;
  }, [sessions, query, sortBy, sortDesc, homeSection, activeSpaceId]);

  const filteredSpaces = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return spaces;
    return spaces.filter((s) => s.name.toLowerCase().includes(q));
  }, [spaces, query]);

  const counts = {
    spaces: spaces.length,
    projects: sessions.filter((s) => !activeSpaceId || s.spaceId === activeSpaceId)
      .length,
    triggers: 0,
  };

  const menuItems: { id: HomeSection; name: string; count: number }[] = [
    { id: "spaces", name: "空间", count: counts.spaces },
    { id: "projects", name: "项目", count: counts.projects },
    { id: "triggers", name: "触发器", count: counts.triggers },
  ];

  const searchPlaceholder =
    (
      {
        spaces: "搜索空间…",
        projects: "搜索项目…",
        triggers: "搜索触发器…",
      } as Record<string, string>
    )[homeSection] || "搜索…";

  const handleSortChange = (next: SortBy) => {
    if (next === sortBy) setSortDesc((v) => !v);
    else {
      setSortBy(next);
      setSortDesc(next !== "name");
    }
    setSortMenuOpen(false);
  };

  return (
    <div className="flex w-full min-w-0 flex-1 flex-col">
      {/* Adapted from eigent HomeHubToolbar sticky offset */}
      <div className="sticky top-[var(--home-hub-history-tabs-offset,49px)] z-10 mb-3 flex w-full flex-wrap items-center justify-between gap-3 bg-ds-bg-neutral-subtle-default pb-3 pt-8">
        <Tabs
          value={homeSection}
          onValueChange={(v) => setHomeSection(v as HomeSection)}
        >
          <TabsList className="gap-1">
            {menuItems.map((menu) => (
              <TabsTrigger
                key={menu.id}
                value={menu.id}
                className="gap-1.5 rounded-lg px-2.5"
              >
                <span className="text-[13px] font-semibold">{menu.name}</span>
                <span className="rounded-full bg-ds-bg-brand-subtle-disabled px-1.5 text-[11px] font-normal tabular-nums text-ds-text-brand-strong-default">
                  {menu.count}
                </span>
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>

        <div className="flex flex-wrap items-center justify-end gap-2">
          <SearchInput
            variant="icon"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={searchPlaceholder}
          />

          <div className="relative">
            <Button
              type="button"
              size="icon"
              variant="ghost"
              title={
                sortBy === "name"
                  ? "按名称"
                  : sortBy === "created"
                    ? "按创建时间"
                    : "按更新时间"
              }
              onClick={() => setSortMenuOpen((v) => !v)}
            >
              <ArrowUpDown className="h-4 w-4" />
            </Button>
            {sortMenuOpen && (
              <>
                <button
                  type="button"
                  className="fixed inset-0 z-10 cursor-default"
                  aria-label="关闭排序"
                  onClick={() => setSortMenuOpen(false)}
                />
                <div className="absolute right-0 z-20 mt-1 w-36 rounded-xl border border-ds-border-neutral-default-default bg-ds-bg-neutral-default-default p-1 shadow-sm">
                  {(
                    [
                      ["created", "创建时间"],
                      ["updated", "更新时间"],
                      ["name", "名称"],
                    ] as const
                  ).map(([id, label]) => (
                    <button
                      key={id}
                      type="button"
                      className={cn(
                        "block w-full rounded-lg px-2 py-1.5 text-left text-xs",
                        sortBy === id
                          ? "bg-ds-bg-neutral-subtle-default font-semibold"
                          : "hover:bg-ds-bg-neutral-subtle-default",
                      )}
                      onClick={() => handleSortChange(id)}
                    >
                      {label}
                      {sortBy === id ? (sortDesc ? " ↓" : " ↑") : ""}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>

          <Tabs
            value={viewMode}
            onValueChange={(v) => setViewMode(v as ViewMode)}
          >
            <TabsList className="h-8 gap-0.5 p-0.5">
              <TabsTrigger value="grid" aria-label="网格" className="px-2">
                <LayoutGrid className="h-4 w-4" />
              </TabsTrigger>
              <TabsTrigger value="list" aria-label="列表" className="px-2">
                <List className="h-4 w-4" />
              </TabsTrigger>
            </TabsList>
          </Tabs>

          <Button
            type="button"
            size="sm"
            onClick={() => {
              createSession();
              setWorkspaceView("workspace");
            }}
          >
            <PlusCircle className="mr-1 h-4 w-4" />
            新建
          </Button>
        </div>
      </div>

      {homeSection === "spaces" && (
        <div
          className={cn(
            viewMode === "list" ? "flex flex-col gap-2" : "grid gap-3 sm:grid-cols-2 lg:grid-cols-3",
          )}
        >
          {filteredSpaces.map((sp) => {
            const count = sessions.filter((s) => s.spaceId === sp.id).length;
            return (
              <div
                key={sp.id}
                className={cn(homeHubSurfaceClass, "group/space-card relative")}
              >
                <button
                  type="button"
                  className="w-full text-left"
                  onClick={() => {
                    setActiveSpace(sp.id);
                    const first = sessions.find((s) => s.spaceId === sp.id);
                    if (first) useSessionsStore.getState().setActive(first.id);
                    else createProject("新对话", { spaceId: sp.id });
                    setWorkspaceView("workspace");
                  }}
                >
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-ds-bg-neutral-subtle-default">
                      <Folder className="h-4 w-4 text-ds-icon-neutral-muted-default" />
                    </div>
                    <div className="min-w-0 flex-1 pr-10">
                      <div className="text-[14px] font-semibold">{sp.name}</div>
                      <div className="mt-1 flex flex-wrap gap-2 text-[12px] text-ds-text-neutral-subtle-default">
                        {sp.id === activeSpaceId && (
                          <span className="rounded-md bg-ds-bg-status-completed-subtle-default px-1.5 py-0.5 text-ds-text-status-completed-default">
                            使用中
                          </span>
                        )}
                        <span>
                          {sp.sourceType === "folder" ? "文件夹" : "空白"}
                        </span>
                        <span>{count} 个项目</span>
                      </div>
                      {sp.rootPath && (
                        <div className="mt-1 truncate font-mono text-[11px] text-ds-text-neutral-subtle-default">
                          {sp.rootPath}
                        </div>
                      )}
                    </div>
                  </div>
                </button>
                <div className="absolute right-3 top-3">
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        type="button"
                        size="icon"
                        variant="ghost"
                        className="h-8 w-8"
                        aria-label="工作空间菜单"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <MoreHorizontal className="h-4 w-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="z-50 min-w-[10rem]">
                      <DropdownMenuItem
                        className="cursor-pointer gap-2"
                        onClick={(e) => {
                          e.stopPropagation();
                          setRenameSpaceTarget(sp);
                          setRenameValue(sp.name);
                        }}
                      >
                        <Pencil className="h-4 w-4" aria-hidden />
                        重命名工作空间
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        className="cursor-pointer gap-2 text-ds-text-error-default-default focus:text-ds-text-error-default-default"
                        disabled={!canDeleteSpace}
                        onClick={(e) => {
                          e.stopPropagation();
                          setDeleteSpaceId(sp.id);
                        }}
                      >
                        <Trash2 className="h-4 w-4 text-ds-text-error-default-default" aria-hidden />
                        删除
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              </div>
            );
          })}
          <button
            type="button"
            className={homeHubSurfaceClass}
            onClick={() => {
              const id = createBlankSpace();
              createProject("新对话", { spaceId: id, workdirMode: "artifact-only" });
              setWorkspaceView("workspace");
            }}
          >
            <div className="flex items-center gap-2 text-[14px] font-semibold">
              <Plus className="h-4 w-4" />
              从空白开始
            </div>
          </button>
          <button
            type="button"
            className={homeHubSurfaceClass}
            onClick={() => {
              void (async () => {
                const dir = await window.api.selectDirectory?.();
                if (!dir) return;
                const name =
                  dir.split(/[/\\]/).filter(Boolean).pop() || "文件夹工作区";
                const id = createFolderSpace(name, dir);
                createProject(name, { spaceId: id, workdirMode: "direct-write" });
                setWorkspaceView("workspace");
              })();
            }}
          >
            <div className="flex items-center gap-2 text-[14px] font-semibold">
              <FolderPlus className="h-4 w-4" />
              选择文件夹…
            </div>
          </button>
        </div>
      )}

      {homeSection === "projects" && (
        <div
          className={cn(
            viewMode === "list"
              ? "flex flex-col gap-2"
              : "grid gap-3 sm:grid-cols-2 lg:grid-cols-3",
          )}
        >
          {filtered.map((s) => (
            <SessionCard
              key={s.id}
              session={s}
              onRequestDelete={setDeleteId}
            />
          ))}
          {!filtered.length && (
            <p className="col-span-full py-12 text-center text-sm text-ds-text-neutral-subtle-default">
              暂无内容，新建一个开始吧。
            </p>
          )}
        </div>
      )}

      {homeSection === "triggers" && (
        <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
          <Zap className="h-8 w-8 text-ds-text-neutral-subtle-default" />
          <p className="text-sm text-ds-text-neutral-muted-default">
            在设置里管理定时任务。
          </p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => usePageTabStore.getState().setHubTab("settings")}
          >
            打开定时任务
          </Button>
        </div>
      )}

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

      <AlertDialog
        open={deleteSpaceId != null}
        title="删除"
        description={
          deleteSpaceTarget
            ? `确定删除「${deleteSpaceTarget.name}」及其下全部项目？此操作不可撤销。不会删除磁盘上的文件夹内容。`
            : "确定删除该工作空间及其下全部项目？此操作不可撤销。"
        }
        confirmLabel="删除"
        confirmVariant="destructive"
        onCancel={() => setDeleteSpaceId(null)}
        onConfirm={() => {
          if (!deleteSpaceId) return;
          const id = deleteSpaceId;
          setDeleteSpaceId(null);
          deleteSpaceCompletely(id);
        }}
      />

      <AlertDialog
        open={renameSpaceTarget != null}
        title="重命名工作空间"
        confirmLabel="保存"
        confirmDisabled={!renameValue.trim()}
        onCancel={() => setRenameSpaceTarget(null)}
        onConfirm={() => {
          const next = renameValue.trim();
          if (!next || !renameSpaceTarget) return;
          renameSpace(renameSpaceTarget.id, next);
          setRenameSpaceTarget(null);
        }}
      >
        <input
          autoFocus
          value={renameValue}
          placeholder="工作空间名称"
          className="h-9 w-full rounded-xl border border-ds-border-neutral-subtle-default bg-ds-bg-neutral-subtle-default px-3 text-sm outline-none focus:ring-2 focus:ring-ds-ring-neutral-subtle-default"
          onChange={(e) => setRenameValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && renameValue.trim() && renameSpaceTarget) {
              renameSpace(renameSpaceTarget.id, renameValue.trim());
              setRenameSpaceTarget(null);
            }
          }}
        />
      </AlertDialog>
    </div>
  );
}
