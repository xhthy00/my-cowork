/**
 * Adapted from eigent: PreviewPanel — Session column; hidden when closed.
 */
import {
  FileText,
  Globe,
  LayoutTemplate,
  Plus,
  RefreshCw,
  TerminalSquare,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import FilePreview from "./FilePreview";
import { getPreviewWebview } from "./PreviewBrowserLayer";
import PreviewBrowserLayer from "./PreviewBrowserLayer";
import PreviewTerminal from "./PreviewTerminal";
import FileTypeIcon from "@/components/files/FileTypeIcon";
import { Button } from "../ui/button";
import { usePageTabStore } from "../../store/pageTab";
import { usePreviewStore, type SessionPreviewTab } from "../../store/preview";
import { cn } from "@/lib/utils";

function ChooserBody() {
  const openBrowser = usePreviewStore((s) => s.openBrowser);
  const openTerminal = usePreviewStore((s) => s.openTerminal);
  const openFile = usePreviewStore((s) => s.openFile);
  return (
    <div className="preview-chooser flex flex-1 flex-col items-center justify-center gap-3">
      <p className="text-sm font-medium text-[var(--text)]">打开新视图</p>
      <Button variant="outline" onClick={() => openBrowser("https://example.com")}>
        浏览器
      </Button>
      <Button variant="outline" onClick={() => openTerminal()}>
        终端
      </Button>
      <Button
        variant="outline"
        onClick={() => {
          void (async () => {
            const res = await window.api.selectFile?.({ title: "选择要预览的文件" });
            const f = res?.files?.[0];
            if (f) openFile(f.filePath, f.fileName);
          })();
        }}
      >
        文件
      </Button>
    </div>
  );
}

function TabBody({ tab }: { tab: SessionPreviewTab }) {
  const refreshKey = tab.refreshKey ?? 0;
  if (tab.type === "chooser") {
    return <ChooserBody />;
  }
  if (tab.type === "browser") {
    return (
      <div className="preview-browser" key={`browser-body-${tab.id}-${refreshKey}`}>
        <div className="preview-browser-bar">
          <input
            className="preview-url"
            defaultValue={tab.url}
            key={tab.navigation.url || tab.url}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                const v = (e.target as HTMLInputElement).value.trim();
                if (v) {
                  const url = /^https?:\/\//i.test(v) ? v : `https://${v}`;
                  usePreviewStore.getState().updateBrowserNav(tab.id, {
                    url,
                    title: url,
                  });
                }
              }
            }}
          />
        </div>
        <div className="preview-browser-host" />
      </div>
    );
  }
  if (tab.type === "file") {
    return (
      <FilePreview
        key={`file-${tab.id}-${refreshKey}`}
        path={tab.path}
        title={tab.title}
        tabId={tab.id}
      />
    );
  }
  return (
    <PreviewTerminal
      key={`term-${tab.id}-${refreshKey}`}
      agentId={tab.agentId}
      taskId={tab.taskId}
    />
  );
}

function TabGlyph({ tab }: { tab: SessionPreviewTab }) {
  if (tab.type === "file") {
    return (
      <FileTypeIcon
        pathOrName={tab.path}
        size="sm"
        className="!h-4 !w-4 !rounded-[4px] [&_svg]:!h-2.5 [&_svg]:!w-2.5"
      />
    );
  }
  if (tab.type === "browser") {
    return <Globe className="h-3.5 w-3.5 shrink-0 text-sky-700" />;
  }
  if (tab.type === "terminal") {
    return <TerminalSquare className="h-3.5 w-3.5 shrink-0 text-emerald-700" />;
  }
  return <LayoutTemplate className="h-3.5 w-3.5 shrink-0 text-ds-icon-neutral-muted-default" />;
}

type CtxMenu = { x: number; y: number; tabId: string };

export default function PreviewPanel() {
  const pageOpen = usePageTabStore((s) => s.previewOpen);
  const setPageOpen = usePageTabStore((s) => s.setPreviewOpen);
  const setSidePanelVisible = usePageTabStore((s) => s.setSidePanelVisible);
  const open = usePreviewStore((s) => s.open);
  const tabs = usePreviewStore((s) => s.tabs);
  const activeTabId = usePreviewStore((s) => s.activeTabId);
  const setOpen = usePreviewStore((s) => s.setOpen);
  const setActiveTab = usePreviewStore((s) => s.setActiveTab);
  const addChooser = usePreviewStore((s) => s.addChooser);
  const closeTab = usePreviewStore((s) => s.closeTab);
  const closeOtherTabs = usePreviewStore((s) => s.closeOtherTabs);
  const closeAllTabs = usePreviewStore((s) => s.closeAllTabs);
  const refreshTab = usePreviewStore((s) => s.refreshTab);
  const isPathDirty = usePreviewStore((s) => s.isPathDirty);
  const [ctx, setCtx] = useState<CtxMenu | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const confirmLeaveTab = (tab: SessionPreviewTab | undefined): boolean => {
    if (tab?.type === "file" && isPathDirty(tab.path)) {
      return window.confirm("表格有未保存的更改，确定离开吗？");
    }
    return true;
  };

  const confirmLeaveMany = (list: SessionPreviewTab[]): boolean => {
    const dirty = list.some((t) => t.type === "file" && isPathDirty(t.path));
    if (!dirty) return true;
    return window.confirm("部分表格有未保存的更改，确定关闭吗？");
  };

  useEffect(() => {
    if (pageOpen && !open) {
      setOpen(true);
      if (!tabs.length) addChooser();
    }
    if (!pageOpen && open) setOpen(false);
  }, [pageOpen, open, setOpen, tabs.length, addChooser]);

  useEffect(() => {
    if (open && !pageOpen) {
      usePageTabStore.getState().openPreviewFoldSide();
    }
  }, [open, pageOpen]);

  useEffect(() => {
    if (!ctx) return;
    const onDown = (e: MouseEvent) => {
      if (menuRef.current?.contains(e.target as Node)) return;
      setCtx(null);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setCtx(null);
    };
    const onScroll = () => setCtx(null);
    window.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    window.addEventListener("scroll", onScroll, true);
    return () => {
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, [ctx]);

  if (!pageOpen) return null;

  const active = tabs.find((t) => t.id === activeTabId) || tabs[0];
  const ctxTab = ctx ? tabs.find((t) => t.id === ctx.tabId) : undefined;

  const runRefresh = (tab: SessionPreviewTab) => {
    if (tab.type === "browser") {
      const el = getPreviewWebview(tab.webviewId) as
        | (HTMLElement & { reload?: () => void })
        | undefined;
      el?.reload?.();
    }
    refreshTab(tab.id);
  };

  return (
    <aside className="preview-panel flex h-full min-h-0 w-full min-w-0 flex-1 flex-col border-l border-ds-border-neutral-subtle-default bg-ds-bg-neutral-default-default">
      <div className="preview-head">
        <div className="preview-tabs">
          {tabs.map((t) => {
            const isActive = t.id === active?.id;
            return (
              <button
                key={t.id}
                type="button"
                className={cn("preview-tab", isActive && "active")}
                title={t.title}
                onClick={() => {
                  if (t.id === active?.id) return;
                  if (!confirmLeaveTab(active)) return;
                  setActiveTab(t.id);
                }}
                onContextMenu={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  const pad = 8;
                  const menuW = 168;
                  const menuH = 168;
                  const x = Math.min(e.clientX, window.innerWidth - menuW - pad);
                  const y = Math.min(e.clientY, window.innerHeight - menuH - pad);
                  setCtx({ x: Math.max(pad, x), y: Math.max(pad, y), tabId: t.id });
                }}
              >
                <TabGlyph tab={t} />
                <span className="preview-tab-label">{t.title}</span>
                <span
                  className="preview-tab-close"
                  title="关闭"
                  onClick={(e) => {
                    e.stopPropagation();
                    const target = tabs.find((x) => x.id === t.id);
                    if (!confirmLeaveTab(target)) return;
                    closeTab(t.id);
                  }}
                >
                  <X className="h-3 w-3" />
                </span>
              </button>
            );
          })}
          <button
            type="button"
            className="preview-tab add"
            title="新建"
            onClick={() => {
              if (!confirmLeaveTab(active)) return;
              addChooser();
            }}
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
        </div>
        <Button
          size="icon"
          variant="ghost"
          className="h-8 w-8 shrink-0"
          title="关闭预览"
          onClick={() => {
            if (!confirmLeaveTab(active)) return;
            setPageOpen(false);
            setOpen(false);
            setSidePanelVisible(true);
          }}
        >
          <X className="h-4 w-4" />
        </Button>
      </div>
      <div className="preview-body relative flex min-h-0 flex-1 flex-col">
        {active ? <TabBody tab={active} /> : null}
        <PreviewBrowserLayer />
      </div>

      {ctx && ctxTab
        ? createPortal(
            <div
              ref={menuRef}
              className="preview-tab-menu"
              style={{ left: ctx.x, top: ctx.y }}
              role="menu"
            >
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  runRefresh(ctxTab);
                  setCtx(null);
                }}
              >
                <RefreshCw className="h-3.5 w-3.5" />
                刷新
              </button>
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  if (!confirmLeaveTab(ctxTab)) return;
                  closeTab(ctxTab.id);
                  setCtx(null);
                }}
              >
                <X className="h-3.5 w-3.5" />
                关闭本页面
              </button>
              <button
                type="button"
                role="menuitem"
                disabled={tabs.length <= 1}
                onClick={() => {
                  const others = tabs.filter((t) => t.id !== ctxTab.id);
                  if (!confirmLeaveMany(others)) return;
                  closeOtherTabs(ctxTab.id);
                  setCtx(null);
                }}
              >
                <FileText className="h-3.5 w-3.5" />
                关闭其他
              </button>
              <div className="preview-tab-menu-sep" />
              <button
                type="button"
                role="menuitem"
                className="is-danger"
                onClick={() => {
                  if (!confirmLeaveMany(tabs)) return;
                  closeAllTabs();
                  setCtx(null);
                  setPageOpen(false);
                  setSidePanelVisible(true);
                }}
              >
                <X className="h-3.5 w-3.5" />
                全部关闭
              </button>
            </div>,
            document.body,
          )
        : null}
    </aside>
  );
}
