/**
 * Adapted from eigent: Session/SidePanelSections/AgentPoolSection.tsx
 * Visual + behavior aligned; toolkit tags when task.toolkits present.
 */
import { AnimatePresence, motion } from "framer-motion";
import { Bot, CodeXml, FileText, Globe, Image, Wrench } from "lucide-react";
import {
  type ReactNode,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from "react";

import ShinyText from "@/components/ui/ShinyText";
import {
  agentMap,
  isWorkflowAgentType,
  type WorkflowAgentType,
} from "@/lib/agentDisplay";
import { cn } from "@/lib/utils";
import type { TaskInfo, WorkforceAgent } from "@/types/workforce";

export const TOOLKIT_MIN_DISPLAY_MS = 1500;
export const TOOLKIT_ROTATION_MS = 2000;

export type AgentToolkit = {
  toolkitName: string;
  toolkitStatus?: string;
  toolkitId?: string;
  toolkitMethods?: string;
};

function hasWork(agent: WorkforceAgent) {
  return Array.isArray(agent.tasks) && agent.tasks.length > 0;
}

function agentHasAnyToolkitsSeen(agent: WorkforceAgent): boolean {
  for (const task of agent.tasks ?? []) {
    for (const tk of task.toolkits ?? []) {
      if (tk.toolkitName && tk.toolkitName !== "notice") return true;
    }
  }
  return false;
}

function sortByAssigned(agents: WorkforceAgent[]): WorkforceAgent[] {
  return [...agents].sort((a, b) => {
    const aHas = hasWork(a);
    const bHas = hasWork(b);
    if (aHas && !bHas) return -1;
    if (!aHas && bHas) return 1;
    return 0;
  });
}

function getAgentSubIcon(agentType: string): ReactNode {
  if (!isWorkflowAgentType(agentType)) return null;
  const preset = agentMap[agentType];
  const iconClass = cn("!h-[10px] !w-[10px] shrink-0", preset.textColor);
  switch (agentType as WorkflowAgentType) {
    case "developer_agent":
      return <CodeXml className={iconClass} />;
    case "browser_agent":
      return <Globe className={iconClass} />;
    case "document_agent":
      return <FileText className={iconClass} />;
    case "multi_modal_agent":
      return <Image className={iconClass} />;
    default:
      return null;
  }
}

function AgentLeadingIcon({ agentType }: { agentType: string }) {
  const subIcon = getAgentSubIcon(agentType);
  return (
    <div className="relative inline-flex h-6 w-6 shrink-0 items-center justify-center self-center rounded-md bg-ds-bg-neutral-subtle-default text-ds-text-neutral-muted-default">
      <Bot className="h-5 w-5" strokeWidth={2} aria-hidden />
      {subIcon != null && (
        <span className="absolute -right-0.5 -top-0.5 inline-flex items-center justify-center [&_svg]:shrink-0">
          {subIcon}
        </span>
      )}
    </div>
  );
}

type ToolkitEntry = {
  id: string;
  name: string;
  firstSeenAt: number;
  expireAt: number | null;
};

type ToolkitState = {
  entries: Map<string, ToolkitEntry>;
  timers: Map<string, ReturnType<typeof setTimeout>>;
  retired: Set<string>;
};

function readToolkitEvents(
  agent: Pick<WorkforceAgent, "tasks"> | undefined,
): Array<{ id: string; name: string; status: string | undefined }> {
  const out: Array<{ id: string; name: string; status: string | undefined }> =
    [];
  for (const task of agent?.tasks ?? []) {
    for (const tk of (task as TaskInfo).toolkits ?? []) {
      if (!tk.toolkitName || tk.toolkitName === "notice") continue;
      const id = String(
        tk.toolkitId ?? `${tk.toolkitName}:${tk.toolkitMethods ?? ""}`,
      );
      out.push({ id, name: tk.toolkitName, status: tk.toolkitStatus });
    }
  }
  return out;
}

/** Exported for unit tests — mirrors Eigent reconcileToolkitState. */
export function reconcileToolkitState(
  state: ToolkitState,
  events: Array<{ id: string; name: string; status: string | undefined }>,
  opts: {
    now: number;
    minDisplayMs: number;
    schedule: (id: string, delayMs: number) => ReturnType<typeof setTimeout>;
    cancel: (handle: ReturnType<typeof setTimeout>) => void;
  },
): string[] {
  for (const event of events) {
    if (state.retired.has(event.id)) continue;
    let entry = state.entries.get(event.id);
    if (!entry) {
      entry = {
        id: event.id,
        name: event.name,
        firstSeenAt: opts.now,
        expireAt: null,
      };
      state.entries.set(event.id, entry);
    }
    if (event.status === "running") {
      if (entry.expireAt !== null) {
        entry.expireAt = null;
        const t = state.timers.get(event.id);
        if (t) {
          opts.cancel(t);
          state.timers.delete(event.id);
        }
      }
    } else if (entry.expireAt === null) {
      const expireAt = Math.max(
        opts.now,
        entry.firstSeenAt + opts.minDisplayMs,
      );
      entry.expireAt = expireAt;
      const delay = Math.max(0, expireAt - opts.now);
      state.timers.set(event.id, opts.schedule(event.id, delay));
    }
  }

  const seen = new Set<string>();
  const out: string[] = [];
  for (const entry of state.entries.values()) {
    if (entry.expireAt !== null && entry.expireAt <= opts.now) continue;
    if (!seen.has(entry.name)) {
      seen.add(entry.name);
      out.push(entry.name);
    }
  }
  return out;
}

export function useLiveToolkits(
  agent: WorkforceAgent,
  minDisplayMs: number = TOOLKIT_MIN_DISPLAY_MS,
): string[] {
  const [, bump] = useReducer((n: number) => n + 1, 0);
  const stateRef = useRef<ToolkitState>({
    entries: new Map(),
    timers: new Map(),
    retired: new Set(),
  });

  const events = readToolkitEvents(agent);
  const names = reconcileToolkitState(stateRef.current, events, {
    // eslint-disable-next-line react-hooks/purity
    now: Date.now(),
    minDisplayMs,
    schedule: (id, delay) =>
      setTimeout(() => {
        stateRef.current.entries.delete(id);
        stateRef.current.timers.delete(id);
        stateRef.current.retired.add(id);
        bump();
      }, delay),
    cancel: clearTimeout,
  });

  useEffect(() => {
    const state = stateRef.current;
    return () => {
      state.timers.forEach(clearTimeout);
      state.timers.clear();
    };
  }, []);

  return names;
}

function AgentToolkitTag({ names }: { names: string[] }) {
  const [focusIndex, setFocusIndex] = useState(0);

  useEffect(() => {
    if (names.length <= 1) {
      setFocusIndex(0);
      return;
    }
    const id = window.setInterval(() => {
      setFocusIndex((i) => (i + 1) % names.length);
    }, TOOLKIT_ROTATION_MS);
    return () => window.clearInterval(id);
  }, [names.length]);

  const focused =
    names.length > 0 ? names[Math.min(focusIndex, names.length - 1)] : null;

  return (
    <div className="inline-flex h-6 min-w-0 shrink-0 items-center overflow-hidden">
      <AnimatePresence initial={false} mode="popLayout">
        {focused && (
          <motion.div
            key={focused}
            initial={{ y: -18, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 18, opacity: 0 }}
            transition={{ duration: 0.28, ease: [0.2, 0, 0.2, 1] }}
            className={cn(
              "inline-flex max-w-full items-center gap-1 rounded-md bg-ds-bg-neutral-muted-default px-1.5 py-0.5 opacity-80",
            )}
            data-testid="agent-toolkit-tag"
          >
            <span className="inline-flex shrink-0 items-center text-ds-text-neutral-default-default [&_svg]:h-4 [&_svg]:w-4">
              <Wrench size={16} aria-hidden />
            </span>
            <ShinyText
              text={focused}
              speed={2.5}
              className="max-w-[140px] truncate text-label-xs font-medium"
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function AgentRow({ agent }: { agent: WorkforceAgent }) {
  const display = isWorkflowAgentType(agent.type)
    ? agentMap[agent.type]
    : undefined;
  const active = hasWork(agent);
  const name = display?.name ?? agent.name;
  const liveToolkits = useLiveToolkits(agent);

  return (
    <div
      className={cn(
        "flex min-w-0 items-center gap-2 rounded-lg bg-ds-bg-neutral-subtle-default px-1.5 py-1.5",
        !active && "opacity-50",
      )}
    >
      <AgentLeadingIcon agentType={agent.type} />
      <span
        className={cn(
          "min-w-0 flex-1 truncate !text-body-sm font-medium text-ds-text-neutral-default-default",
          display?.textColor,
        )}
      >
        {name}
      </span>
      <AgentToolkitTag names={liveToolkits} />
    </div>
  );
}

function AgentList({ agents }: { agents: WorkforceAgent[] }) {
  return (
    <motion.ul layout className="m-0 flex list-none flex-col gap-2 p-0">
      <AnimatePresence initial={false} mode="popLayout">
        {agents.map((agent) => (
          <motion.li
            key={agent.agent_id}
            layout
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
          >
            <AgentRow agent={agent} />
          </motion.li>
        ))}
      </AnimatePresence>
    </motion.ul>
  );
}

interface AgentPoolSectionProps {
  title: string;
  agents: WorkforceAgent[];
  /** Render accordion chrome; parent AccordionBox supplies open state via children fn. */
  open: boolean;
}

/** Body only — pair with AccordionBox render-prop / title. */
export function AgentPoolBody({ agents, open }: Omit<AgentPoolSectionProps, "title">) {
  const ordered = useMemo(() => sortByAssigned(agents), [agents]);
  const activeAgents = useMemo(() => ordered.filter(hasWork), [ordered]);
  const toolingAgents = useMemo(
    () => ordered.filter(agentHasAnyToolkitsSeen),
    [ordered],
  );

  if (ordered.length === 0) {
    return open ? (
      <div className="px-1 py-1 text-body-sm text-ds-text-neutral-subtle-default">
        No agents yet
      </div>
    ) : null;
  }
  if (!open) {
    const collapsed =
      toolingAgents.length > 0 ? toolingAgents : activeAgents;
    return collapsed.length > 0 ? <AgentList agents={collapsed} /> : null;
  }
  return <AgentList agents={ordered} />;
}
