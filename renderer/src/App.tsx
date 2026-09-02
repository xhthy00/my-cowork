import { useEffect } from "react";

import ChatView from "./components/ChatView";
import PreviewPanel from "./components/preview/PreviewPanel";
import SessionSidePanel from "./components/session/SessionSidePanel";
import WorkspaceSessionLayout from "./components/workspace/WorkspaceSessionLayout";
import WorkspaceShell from "./components/workspace/WorkspaceShell";
import HubView from "./components/hub/HubView";
import ProjectSidebar from "./components/shell/ProjectSidebar";
import TopBar from "./components/shell/TopBar";
import TitleBar from "./components/TitleBar";
import { usePageTabStore } from "./store/pageTab";
import { useSessionStore } from "./store/session";
import {
  ensureActiveSession,
  useSessionsStore,
} from "./store/sessions";

/**
 * Adapted from eigent Layout + Workspace:
 * muted chrome · TopBar · rounded sidebar + subtle workspace surface
 */
export default function App() {
  const workspaceView = usePageTabStore((s) => s.workspaceView);
  const activeId = useSessionsStore((s) => s.activeId);
  const messageCount = useSessionStore((s) => s.messages.length);

  useEffect(() => {
    ensureActiveSession();
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
      <TitleBar />
      <TopBar />
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
