/**
 * Adapted from eigent Terminal / TerminalAgentWorkspace — real xterm stream.
 */
import { useEffect, useMemo, useRef } from "react";
import { Terminal } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";

import { useWorkforceStore } from "../../store/workforce";

interface Props {
  agentId?: string;
  taskId?: string;
}

export default function PreviewTerminal({ agentId, taskId }: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<Terminal | null>(null);
  const writtenRef = useRef(0);

  const agents = useWorkforceStore((s) => s.taskAssigning);
  const agent =
    agents.find((a) => a.agent_id === agentId) ||
    agents.find((a) => a.status === "running");

  const joined = useMemo(() => {
    if (!agent?.tasks.length) return "";
    const filtered = taskId
      ? agent.tasks.filter((t) => t.id === taskId)
      : agent.tasks;
    // assign_id / session id mismatch → fall back to all of this agent's output
    const tasks =
      filtered.length > 0 && filtered.some((t) => (t.terminal || []).length)
        ? filtered
        : agent.tasks;
    return tasks.flatMap((t) => t.terminal || []).join("");
  }, [agent, taskId]);

  useEffect(() => {
    if (!hostRef.current || termRef.current) return;
    const term = new Terminal({
      convertEol: true,
      fontSize: 12,
      theme: { background: "#1a1a1a", foreground: "#d6d6d6" },
    });
    term.open(hostRef.current);
    termRef.current = term;
    return () => {
      term.dispose();
      termRef.current = null;
      writtenRef.current = 0;
    };
  }, []);

  useEffect(() => {
    const term = termRef.current;
    if (!term) return;
    if (joined.length <= writtenRef.current) return;
    term.write(joined.slice(writtenRef.current));
    writtenRef.current = joined.length;
  }, [joined]);

  return <div ref={hostRef} className="preview-xterm" />;
}
