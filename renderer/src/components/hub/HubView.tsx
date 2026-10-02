/** Workspace catalog pages share the sidebar and scroll surface. */
import { useEffect, useState } from "react";
import { Link2 } from "lucide-react";

import HomeHub from "@/components/hub/HomeHub";
import IndustryWorkbench from "@/components/hub/IndustryWorkbench";
import AssistantsView from "@/components/hub/AssistantsView";
import SkillsView from "@/components/skills/SkillsView";
import SkillStoreView from "@/components/skills/SkillStoreView";
import MemoryView from "@/components/memory/MemoryView";
import McpConnectorsPanel from "@/components/settings/McpConnectorsPanel";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import {
  usePageTabStore,
  type AgentsSection,
  type HubTab,
} from "@/store/pageTab";

function AgentsHub() {
  const section = usePageTabStore((s) => s.agentsSection);
  const setSection = usePageTabStore((s) => s.setAgentsSection);
  const items = [
    ["sub-agents", "助理"],
    ["skills", "技能"],
    ["skill-store", "skill商店"],
    ["memory", "记忆"],
  ] as const;

  return (
    <Tabs
      value={section}
      onValueChange={(v) => setSection(v as AgentsSection)}
      className="agents-hub flex h-auto w-full flex-col"
    >
      {/* Adapted from eigent VerticalNav — ghost tabs: white chip on grey page */}
      <aside className="agents-section-nav sticky top-0 z-20 flex w-full shrink-0 self-start py-4">
        <TabsList appearance="ghost" className="w-full flex-row gap-2">
          {items.map(([id, label]) => (
            <TabsTrigger key={id} value={id}>
              {label}
            </TabsTrigger>
          ))}
        </TabsList>
        <Button variant="ghost" onClick={() => usePageTabStore.getState().setHubTab("connectors")}><Link2 className="h-4 w-4" aria-hidden />连接器</Button>
      </aside>
      <div className="flex h-auto w-full min-w-0 flex-1 flex-col">
        {section === "skills" && <SkillsView />}
        {section === "skill-store" && <SkillStoreView />}
        {section === "memory" && <MemoryView />}
        {section === "sub-agents" && <AssistantsView />}
      </div>
    </Tabs>
  );
}

function ConnectorsHub() {
  return (
    <div className="m-auto flex h-auto w-full flex-1 flex-col">
      <McpConnectorsPanel />
    </div>
  );
}

export default function HubView() {
  const hubTab = usePageTabStore((s) => s.hubTab);
  const homeSection = usePageTabStore((s) => s.homeSection);
  const [visited, setVisited] = useState<HubTab[]>([hubTab]);

  useEffect(() => {
    setVisited((prev) => (prev.includes(hubTab) ? prev : [...prev, hubTab]));
  }, [hubTab]);

  return (
    <div className="hub-view flex h-full w-full flex-1 flex-col px-1 pb-1">
      <div className={cn("scrollbar-hide h-full rounded-2xl bg-ds-bg-neutral-subtle-default", hubTab === "workbench" || (hubTab === "home" && homeSection !== "triggers") ? "flex min-h-0 flex-col overflow-hidden" : "overflow-y-auto")}>
        {visited.includes("home") && (
          <div
            className={hubTab === "home" ? cn("flex w-full px-[var(--hub-gutter)]", homeSection === "triggers" ? "automation-hub h-auto pb-[120px]" : "h-full min-h-0 flex-1 pb-6") : "hidden"}
            aria-hidden={hubTab !== "home"}
          >
            <HomeHub />
          </div>
        )}

        {visited.includes("workbench") && (
          <div
            className={hubTab === "workbench" ? "flex min-h-0 w-full flex-1" : "hidden"}
            aria-hidden={hubTab !== "workbench"}
          >
            <IndustryWorkbench />
          </div>
        )}

        <div className={cn("m-auto h-auto w-full max-w-[1600px] flex-1 flex-col", hubTab === "workbench" || hubTab === "home" ? "hidden" : "flex")}>
          <div className="flex h-auto w-full hub-content flex-col px-6 pb-12">
            {visited.includes("agents") && (
              <div className={hubTab === "agents" ? "contents" : "hidden"} aria-hidden={hubTab !== "agents"}>
                <AgentsHub />
              </div>
            )}
            {visited.includes("connectors") && (
              <div
                className={hubTab === "connectors" ? "contents" : "hidden"}
                aria-hidden={hubTab !== "connectors"}
              >
                <ConnectorsHub />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
