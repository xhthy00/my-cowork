import { useEffect, useRef, useState } from "react";
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
  const activeId = useSessionsStore((s) => s.activeId);
  const messageCount = useSessionStore((s) => s.messages.length);
  const [backendReady, setBackendReady] = useState(false);
  // First run without an API key: keep the UI usable so Settings is reachable.
  const [needsModel, setNeedsModel] = useState(false);
  const routedToModels = useRef(false);
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
    let changed = false;
    const offReady =
      window.api.onBackendReady?.((url) => {
        changed = true;
        setBackendReady(true);
        setNeedsModel(false);
        if (url) void connectDesktopSessionSync(url);
      }) ?? (() => {});
    const enterNeedsModel = () => {
      changed = true;
      setBackendReady(false);
      setNeedsModel(true);
      if (routedToModels.current) return;
      routedToModels.current = true;
      window.dispatchEvent(new CustomEvent("my-cowork:navigate", { detail: "models" }));
    };
    // The event may fire before this listener exists, so also ask for the current state.
    const offNeedsModel = window.api.onBackendNeedsModel?.(enterNeedsModel) ?? (() => {});
    const offFailed = window.api.onBackendFailed?.(() => {
      changed = true;
      setBackendReady(false); setNeedsModel(false);
    }) ?? (() => {});
    const offStarting = window.api.onBackendStarting?.(() => {
      changed = true;
      setBackendReady(false); setNeedsModel(false);
    }) ?? (() => {});
    void Promise.all([window.api.getBackendStatus?.(), window.api.getBackendUrl()]).then(([status, url]) => {
      if (changed) return;
      if (status?.state === "needs-model") enterNeedsModel();
      else if (url && (!status || status.state === "ready")) {
        setBackendReady(true);
        void connectDesktopSessionSync(url);
      }
    }).catch(() => {});
    return () => {
      changed = true;
      offReady();
      offNeedsModel();
      offFailed();
      offStarting();
    };
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
        usePageTabStore.getState().setHubTab("settings");
      } else if (detail === "settings-general") {
        usePageTabStore.getState().setHubTab("settings");
      } else if (detail === "settings-schedule") {
        usePageTabStore.getState().setHubTab("settings");
      } else if (detail === "models") {
        usePageTabStore.getState().setHubTab("settings");
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
    <div className="window font-sans bg-ds-bg-neutral-muted-default">
      {automationNotice ? <button type="button" className="fixed right-5 top-16 z-[120] max-w-sm rounded-2xl border border-violet-200 bg-ds-bg-neutral-subtle-default dark:border-violet-700 px-4 py-3 text-left text-sm font-medium text-ds-text-neutral-default-default shadow-xl" onClick={() => { setAutomationNotice(""); usePageTabStore.getState().setHubTab("home"); usePageTabStore.getState().setHomeSection("triggers"); }}>{automationNotice}<span className="ml-2 text-ds-text-brand-default-default">查看</span></button> : null}
      {needsModel && !backendReady ? <button type="button" className="fixed left-1/2 top-16 z-[120] max-w-md -translate-x-1/2 rounded-2xl border border-violet-200 bg-ds-bg-neutral-subtle-default dark:border-violet-700 px-4 py-3 text-left text-sm font-medium text-ds-text-neutral-default-default shadow-xl" onClick={() => window.dispatchEvent(new CustomEvent("my-cowork:navigate", { detail: "models" }))}>还没有配置模型，填写 API 密钥后即可开始使用<span className="ml-2 text-ds-text-brand-default-default">去配置</span></button> : null}
      {!backendReady && !needsModel && <StartupSplash />}
      <TitleBar />
      <TopBar />
      {waitingAppTask && <button type="button" className="shrink-0 border-b border-ds-border-neutral-subtle-default bg-ds-bg-neutral-default-default px-4 py-1.5 text-left text-xs" onClick={() => expandAppTask(waitingAppTask)}>{waitingAppTask.origin.app_name} · 有 AI 任务待处理 <span className="text-ds-text-brand-default-default">查看</span></button>}
      <div className="body">
        {/* Eigent /history is full-width (no ProjectSidebar); Workspace keeps left rail */}
        {workspaceView === "hub" ? (
          <div className="min-w-0 flex-1 overflow-hidden">
            <HubView />
          </div>
        ) : (
          <WorkspaceShell
            sidebar={<ProjectSidebar fill />}
            main={
              <WorkspaceSessionLayout
                chat={<ChatView />}
                preview={<PreviewPanel />}
                side={messageCount === 0 ? null : <SessionSidePanel />}
              />
            }
          />
        )}
      </div>
    </div>
  );
}
