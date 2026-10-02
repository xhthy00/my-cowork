import { useEffect, useState } from "react";
import { automationApi, type Automation } from "./api/automations";
import { watchAppTasks, useAppTasks } from "./api/industryAI";
import { expandAppTask } from "./components/hub/IndustryAIPanel";

import ChatView from "./components/ChatView";
import PreviewPanel from "./components/preview/PreviewPanel";
import SessionSidePanel from "./components/session/SessionSidePanel";
import WorkspaceSessionLayout from "./components/workspace/WorkspaceSessionLayout";
import WorkspaceShell from "./components/workspace/WorkspaceShell";
import HubView from "./components/hub/HubView";
import ProjectSidebar from "./components/shell/ProjectSidebar";
import StartupSplash from "./components/StartupSplash";
import TopBar from "./components/shell/TopBar";
import TitleBar from "./components/TitleBar";
import SettingsDialog from "./components/settings/SettingsDialog";
import { usePageTabStore } from "./store/pageTab";
import { useIndustryNavigation } from "./store/industryNavigation";
import { useSessionStore } from "./store/session";
import { connectDesktopSessionSync, initDesktopSessionSync } from "./store/desktopSessionSync";
import {
  useSessionsStore,
} from "./store/sessions";

/**
 * Adapted from eigent Layout + Workspace:
 * muted chrome · TopBar · rounded sidebar + subtle workspace surface
 */
export default function App() {
  const workspaceView = usePageTabStore((s) => s.workspaceView);
  const hubTab = usePageTabStore((s) => s.hubTab);
  const activeAppId = useIndustryNavigation((s) => s.activeId);
  const industryFullscreen = workspaceView === "hub" && hubTab === "workbench" && activeAppId !== null;
  const activeId = useSessionsStore((s) => s.activeId);
  const messageCount = useSessionStore((s) => s.messages.length);
  const previewOpen = usePageTabStore((s) => s.previewOpen);
  const sidePanelVisible = usePageTabStore((s) => s.sidePanelVisible);
  const [backendReady, setBackendReady] = useState(false);
  const [automationNotice, setAutomationNotice] = useState("");
  const appTasks = useAppTasks(state => state.records);
  const waitingAppTask = Object.values(appTasks).find(task => task.waiting
    && !(workspaceView === "hub" && hubTab === "workbench" && activeAppId === task.origin.app_id)
    && !(workspaceView === "workspace" && activeId === task.origin.project_id));

  useEffect(() => {
    if (backendReady) return watchAppTasks();
  }, [backendReady]);

  useEffect(() => {
    if (!backendReady) return;
    let prior: Map<string, string> | null = null;
    let dismissed: ReturnType<typeof setTimeout> | null = null;
    const check = async () => {
      try {
        const { tasks } = await automationApi<{ tasks: Automation[] }>("");
        const current = new Map<string, string>();
        for (const task of tasks) {
          const active = task.active_run;
          const marker = active ? `${active.run_id}:${active.status}` : `${task.last_run || 0}:${task.last_status || ""}`;
          current.set(task.id, marker);
          const needsAttention = active?.status === "waiting_user" || active?.status === "recovery_review";
          if ((!prior && needsAttention) || (prior && prior.get(task.id) !== marker && (task.notify_on_completion || needsAttention))) {
            const action = active?.status === "recovery_review" ? "需要检查恢复" :
              active?.status === "waiting_user" ? "需要你的回复" :
              task.last_status === "error" ? "执行失败" : task.last_status === "ok" ? "已完成" : "已开始";
            setAutomationNotice(`${task.title} · ${action}`);
            if (dismissed) clearTimeout(dismissed);
            dismissed = setTimeout(() => setAutomationNotice(""), 6500);
          }
        }
        prior = current;
      } catch { /* Offline state is shown by the task page. */ }
    };
    void check();
    const timer = setInterval(() => void check(), 5000);
    return () => { clearInterval(timer); if (dismissed) clearTimeout(dismissed); };
  }, [backendReady]);

  useEffect(() => {
    initDesktopSessionSync();
    // Already up (restart / fast boot)? Skip splash.
    void window.api.getBackendUrl().then((url) => {
      if (url) {
        void connectDesktopSessionSync(url).finally(() => setBackendReady(true));
      }
    });
    const offReady =
      window.api.onBackendReady?.((url) => {
        if (url) void connectDesktopSessionSync(url).finally(() => setBackendReady(true));
      }) ?? (() => {});
    return offReady;
  }, []);

  useEffect(() => {
    const onNav = (e: Event) => {
      const detail = (e as CustomEvent<string>).detail;
      if (detail === "skills") {
        usePageTabStore.getState().setHubTab("agents");
        usePageTabStore.getState().setAgentsSection("skills");
      } else if (detail === "memory") {
        usePageTabStore.getState().setHubTab("agents");
        usePageTabStore.getState().setAgentsSection("memory");
      } else if (detail === "settings") {
        usePageTabStore.getState().openSettings();
      } else if (detail === "settings-general") {
        usePageTabStore.getState().openSettings();
      } else if (detail === "settings-schedule") {
        usePageTabStore.getState().openSettings("schedule");
      } else if (detail === "models") {
        usePageTabStore.getState().openSettings("model");
      } else if (detail === "browser") {
        usePageTabStore.getState().setHubTab("browser");
      } else if (detail === "connectors") {
        usePageTabStore.getState().setHubTab("connectors");
      } else if (detail === "knowledge") {
        usePageTabStore.getState().setHubTab("knowledge");
      } else if (detail === "home") {
        usePageTabStore.getState().setHubTab("home");
      }
    };
    window.addEventListener("my-cowork:navigate", onNav);
    return () => window.removeEventListener("my-cowork:navigate", onNav);
  }, []);

  return (
    <div className="window font-sans bg-ds-bg-neutral-muted-default" data-industry-fullscreen={industryFullscreen}>
      {automationNotice ? <button type="button" className="fixed right-5 top-16 z-[120] max-w-sm rounded-2xl border border-violet-200 bg-white px-4 py-3 text-left text-sm font-medium text-ds-text-neutral-default-default shadow-xl" onClick={() => { setAutomationNotice(""); usePageTabStore.getState().setHubTab("home"); usePageTabStore.getState().setHomeSection("triggers"); }}>{automationNotice}<span className="ml-2 text-violet-700">查看</span></button> : null}
      {!backendReady && <StartupSplash />}
      <TitleBar />
      <SettingsDialog />
      {waitingAppTask && <button type="button" className="shrink-0 border-b border-ds-border-neutral-subtle-default bg-ds-bg-neutral-default-default px-4 py-1.5 text-left text-xs" onClick={() => expandAppTask(waitingAppTask)}>{waitingAppTask.origin.app_name} · 有 AI 任务待处理 <span className="text-ds-text-brand-default-default">查看</span></button>}
      <div className="body">
        <WorkspaceShell
          industryFullscreen={industryFullscreen}
          sidebar={<div className="app-sidebar flex h-full min-h-0 flex-col"><TopBar /><ProjectSidebar fill /></div>}
          main={workspaceView === "hub" ? <HubView /> : (
            <WorkspaceSessionLayout
              chat={<ChatView />}
              preview={<PreviewPanel />}
              side={messageCount === 0 || (previewOpen && !sidePanelVisible) ? null : <SessionSidePanel />}
            />
          )}
        />
      </div>
    </div>
  );
}
