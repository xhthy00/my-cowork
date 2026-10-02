import * as Dialog from "@radix-ui/react-dialog";
import { useCompactLayout } from "@/hooks/useCompactLayout";
import { PanelLeft, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { usePageTabStore } from "@/store/pageTab";
import { useSessionsStore } from "@/store/sessions";
import { useIndustryNavigation } from "@/store/industryNavigation";

/** Sidebar utilities stay available on every page. */
export default function TopBar() {
  const sidebarFolded = usePageTabStore(s => s.projectSidebarFolded);
  const compact = useCompactLayout();
  const folded = sidebarFolded || compact;
  const toggle = usePageTabStore(s => s.toggleProjectSidebar);
  const sessions = useSessionsStore(s => s.sessions);
  const searchTriggerRef = useRef<HTMLButtonElement>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState("");
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const page = usePageTabStore.getState();
      if (page.workspaceView === "hub" && page.hubTab === "workbench" && useIndustryNavigation.getState().activeId) return;
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setSearchOpen(v => !v); }
      if (e.key === "Escape") setSearchOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const filtered = useMemo(() => sessions.filter(s => s.title.toLowerCase().includes(query.trim().toLowerCase())).slice(0, 8), [query, sessions]);
  return <header data-folded={folded} className="app-topbar flex shrink-0 items-center justify-end gap-2 px-4">
    <Button size="icon" variant="ghost" disabled={compact} aria-label={folded ? "展开侧栏" : "折叠侧栏"} aria-expanded={!folded} onClick={toggle}><PanelLeft size={18} aria-hidden /></Button>
    <Button ref={searchTriggerRef} size="icon" variant="ghost" aria-label="搜索任务" title="搜索任务 (⌘K)" aria-expanded={searchOpen} onClick={() => setSearchOpen(v => !v)}><Search size={18} aria-hidden /></Button>
    <Dialog.Root open={searchOpen} onOpenChange={setSearchOpen}><Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-[140] bg-black/15" /><Dialog.Content onCloseAutoFocus={event => { event.preventDefault(); searchTriggerRef.current?.focus(); }} aria-describedby={undefined} className="task-search-dialog">
      <div className="mb-3 flex items-center justify-between"><Dialog.Title className="font-semibold">搜索任务</Dialog.Title><Button size="sm" variant="ghost" onClick={() => setSearchOpen(false)}>关闭</Button></div>
      <input autoFocus aria-label="任务名称" className="mb-3 w-full rounded-xl border border-ds-border-neutral-default-default bg-ds-bg-neutral-subtle-default px-3 py-3 text-sm" placeholder="输入任务名称…" value={query} onChange={e => setQuery(e.target.value)} />
      <div className="max-h-64 space-y-1 overflow-y-auto">{filtered.map(s => <button key={s.id} type="button" className="flex w-full items-center justify-between rounded-xl px-3 py-3 text-left text-sm hover:bg-ds-bg-neutral-subtle-default" onClick={() => { usePageTabStore.getState().setWorkspaceView("workspace"); if (usePageTabStore.getState().workspaceView !== "workspace") return; useSessionsStore.getState().setActive(s.id); setSearchOpen(false); setQuery(""); }}><span className="truncate">{s.title}</span></button>)}{!filtered.length && <p className="px-3 py-4 text-sm text-ds-text-neutral-muted-default">没有找到匹配的任务</p>}</div>
    </Dialog.Content></Dialog.Portal></Dialog.Root>
  </header>;
}
