/**
 * Adapted from eigent: TopBar — fold, home, SpaceSwitchDropdown, utilities.
 */
import {
  ChevronsUpDown,
  Folder,
  Home,
  PanelLeft,
  PanelLeftClose,
  Search,
  Settings,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import SpaceSwitchDropdown from "@/components/shell/SpaceSwitchDropdown";
import AlertDialog from "@/components/ui/alertDialog";
import { Button } from "@/components/ui/button";
import { usePageTabStore } from "@/store/pageTab";
import { ensureActiveSession, useSessionsStore } from "@/store/sessions";
import { useSpacesStore } from "@/store/spaces";

const isElectron =
  typeof navigator !== "undefined" && /Electron/i.test(navigator.userAgent);

export default function TopBar() {
  const folded = usePageTabStore((s) => s.projectSidebarFolded);
  const toggle = usePageTabStore((s) => s.toggleProjectSidebar);
  const setWorkspaceView = usePageTabStore((s) => s.setWorkspaceView);
  const setHubTab = usePageTabStore((s) => s.setHubTab);
  const workspaceView = usePageTabStore((s) => s.workspaceView);
  const sessions = useSessionsStore((s) => s.sessions);
  const setActive = useSessionsStore((s) => s.setActive);
  const createProject = useSessionsStore((s) => s.createProject);
  const spaces = useSpacesStore((s) => s.spaces);
  const activeSpaceId = useSpacesStore((s) => s.activeSpaceId);
  const setActiveSpace = useSpacesStore((s) => s.setActiveSpace);
  const createBlankSpace = useSpacesStore((s) => s.createBlankSpace);
  const createFolderSpace = useSpacesStore((s) => s.createFolderSpace);
  const renameSpace = useSpacesStore((s) => s.renameSpace);
  const activeSpaceName =
    spaces.find((x) => x.id === activeSpaceId)?.name || "工作区";

  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [renameOpen, setRenameOpen] = useState(false);
  const [renameValue, setRenameValue] = useState("");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSearchOpen((v) => !v);
      }
      if (e.key === "Escape") setSearchOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return sessions.slice(0, 8);
    return sessions.filter((s) => s.title.toLowerCase().includes(q)).slice(0, 8);
  }, [query, sessions]);

  function selectSpace(spaceId: string) {
    setActiveSpace(spaceId);
    const first = useSessionsStore.getState().projectsForSpace(spaceId)[0];
    if (first) setActive(first.id);
    else createProject("新对话", { spaceId });
    setWorkspaceView("workspace");
  }

  async function pickFolderSpace() {
    const dir = await window.api.selectDirectory?.();
    if (!dir) return;
    const name = dir.split(/[/\\]/).filter(Boolean).pop() || "文件夹工作区";
    const spaceId = createFolderSpace(name, dir);
    createProject(name, { spaceId, workdirMode: "direct-write" });
    setWorkspaceView("workspace");
  }

  function openRename() {
    setRenameValue(activeSpaceName);
    setRenameOpen(true);
  }

  function confirmRename() {
    const next = renameValue.trim();
    if (!next || !activeSpaceId) return;
    renameSpace(activeSpaceId, next);
    setRenameOpen(false);
  }

  return (
    <header
      className={`relative z-50 flex h-10 shrink-0 items-center gap-1 py-1 ${
        isElectron ? "pl-[72px] pr-2" : "px-2"
      }`}
      style={{ WebkitAppRegion: "drag" } as React.CSSProperties}
    >
      <div
        className="flex min-w-0 items-center gap-0.5"
        style={{ WebkitAppRegion: "no-drag" } as React.CSSProperties}
      >
        <Button size="icon" variant="ghost" title="折叠侧栏" onClick={() => toggle()}>
          {folded ? <PanelLeft className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
        </Button>
        {workspaceView === "hub" ? (
          <button
            type="button"
            onClick={() => setWorkspaceView("workspace")}
            className="flex min-h-[28px] items-center gap-1.5 rounded-full px-2 text-label-sm font-bold text-ds-text-neutral-default-default outline-none transition-colors hover:bg-ds-bg-neutral-default-hover"
          >
            <Home className="h-4 w-4 shrink-0" aria-hidden />
            返回工作区
          </button>
        ) : (
          <>
            <button
              type="button"
              onClick={() => {
                setHubTab("home");
                usePageTabStore.getState().setHomeSection("spaces");
              }}
              aria-label="AI 主页"
              className="flex min-h-[28px] items-center gap-1.5 rounded-full px-2 text-label-sm font-bold text-ds-text-neutral-default-default outline-none transition-colors hover:bg-ds-bg-neutral-default-hover"
            >
              <Home className="h-4 w-4 shrink-0" aria-hidden />
              AI 主页
            </button>
            <SpaceSwitchDropdown
              contentAlign="start"
              spaces={spaces}
              activeSpaceId={activeSpaceId}
              onSpaceSelect={selectSpace}
              onRenameSpace={openRename}
              onStartFromScratch={() => {
                const id = createBlankSpace();
                createProject("新对话", {
                  spaceId: id,
                  workdirMode: "artifact-only",
                });
                setWorkspaceView("workspace");
              }}
              onSelectFolder={() => void pickFolderSpace()}
              trigger={
                <button
                  type="button"
                  className="flex min-h-[28px] min-w-0 items-center gap-1.5 rounded-full px-2 text-label-sm font-bold text-ds-text-neutral-default-default outline-none transition-colors hover:bg-ds-bg-neutral-default-hover"
                  aria-haspopup="menu"
                  aria-label={activeSpaceName}
                >
                  <Folder className="h-4 w-4 shrink-0" aria-hidden />
                  <span className="min-w-0 max-w-[220px] overflow-hidden text-ellipsis whitespace-nowrap">
                    {activeSpaceName}
                  </span>
                  <ChevronsUpDown
                    className="h-3.5 w-3.5 shrink-0 text-ds-icon-neutral-subtle-default"
                    aria-hidden
                  />
                </button>
              }
            />
          </>
        )}
      </div>

      <div className="h-7 min-w-0 flex-1" aria-hidden />

      <div
        className="flex items-center gap-0.5"
        style={{ WebkitAppRegion: "no-drag" } as React.CSSProperties}
      >
        <Button
          size="icon"
          variant="ghost"
          title="搜索会话 (⌘K)"
          onClick={() => setSearchOpen((v) => !v)}
        >
          <Search className="h-4 w-4" />
        </Button>
        <Button size="icon" variant="ghost" title="设置" onClick={() => setHubTab("settings")}>
          <Settings className="h-4 w-4" />
        </Button>
      </div>

      {searchOpen && (
        <div
          className="absolute left-1/2 top-11 z-50 w-[min(420px,90vw)] -translate-x-1/2 rounded-2xl border border-ds-border-neutral-default-default bg-ds-bg-neutral-default-default p-3 shadow-soft"
          style={{ WebkitAppRegion: "no-drag" } as React.CSSProperties}
        >
          <input
            autoFocus
            className="mb-2 w-full rounded-xl border border-ds-border-neutral-default-default bg-ds-bg-neutral-subtle-default px-3 py-2 text-sm outline-none"
            placeholder="搜索会话…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <div className="max-h-64 space-y-1 overflow-y-auto">
            {filtered.map((s) => (
              <button
                key={s.id}
                type="button"
                className="flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-sm hover:bg-ds-bg-neutral-subtle-default"
                onClick={() => {
                  setActive(s.id);
                  setWorkspaceView("workspace");
                  ensureActiveSession();
                  setSearchOpen(false);
                  setQuery("");
                }}
              >
                <span className="truncate font-medium">{s.title}</span>
                <span className="text-[11px] text-ds-text-neutral-subtle-default">
                  {s.status}
                </span>
              </button>
            ))}
            {!filtered.length && (
              <p className="px-2 py-3 text-xs text-ds-text-neutral-subtle-default">
                无匹配会话
              </p>
            )}
          </div>
        </div>
      )}

      <AlertDialog
        open={renameOpen}
        title="重命名工作空间"
        confirmLabel="保存"
        confirmDisabled={!renameValue.trim()}
        onCancel={() => setRenameOpen(false)}
        onConfirm={confirmRename}
      >
        <input
          autoFocus
          value={renameValue}
          placeholder="工作空间名称"
          className="h-9 w-full rounded-xl border border-ds-border-neutral-subtle-default bg-ds-bg-neutral-subtle-default px-3 text-sm outline-none focus:ring-2 focus:ring-ds-ring-neutral-subtle-default"
          onChange={(e) => setRenameValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && renameValue.trim()) confirmRename();
          }}
        />
      </AlertDialog>
    </header>
  );
}
