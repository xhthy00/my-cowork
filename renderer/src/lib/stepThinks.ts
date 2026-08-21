/**
 * Per-step thinking from SSE step.delta (backend wraps reasoning in <think>).
 * Each think belongs to the tool call it immediately precedes.
 */
import type { TraceEvent } from "../store/session";

export type StepThink = {
  id: string;
  agentId: string;
  /** Tool call / work-log row this think sits under. */
  stepId?: string;
  text: string;
  closed: boolean;
};

function extractThinkBody(raw: string): { text: string; closed: boolean } {
  const src = raw || "";
  if (!src.trim()) return { text: "", closed: true };

  const hasOpen = /<\s*think\b/i.test(src);
  const hasClose = /<\s*\/\s*think(?:ing)?\s*>/i.test(src);

  if (!hasOpen && hasClose) {
    const text = src.replace(/<\s*\/\s*think(?:ing)?\s*>[\s\S]*$/i, "").trim();
    return { text, closed: true };
  }

  const blocks: string[] = [];
  const re = /<think>([\s\S]*?)<\/think>/gi;
  let m: RegExpExecArray | null;
  while ((m = re.exec(src))) {
    const body = m[1].trim();
    if (body) blocks.push(body);
  }
  const afterClosed = src.replace(/<think>[\s\S]*?<\/think>/gi, "");
  const open = afterClosed.match(/<think>([\s\S]*)$/i);
  if (open) {
    const body = open[1].trim();
    if (body) blocks.push(body);
    return { text: blocks.join("\n\n").trim(), closed: false };
  }
  if (blocks.length) return { text: blocks.join("\n\n").trim(), closed: true };
  return { text: "", closed: true };
}

type Bucket = {
  id: string;
  agentId: string;
  stepId?: string;
  raw: string;
  closed: boolean;
};

function toThink(b: Bucket): StepThink | null {
  const { text, closed } = extractThinkBody(b.raw);
  if (text) {
    return {
      id: b.id,
      agentId: b.agentId,
      stepId: b.stepId,
      text,
      closed: closed || b.closed,
    };
  }
  if (!b.closed && b.raw.trim()) {
    return {
      id: b.id,
      agentId: b.agentId,
      stepId: b.stepId,
      text: b.raw.trim(),
      closed: false,
    };
  }
  return null;
}

/**
 * One think block per agent turn. The turn is bound to the *next* tool
 * (the call the model was thinking about), not the graph.step node.
 */
export function collectStepThinks(trace: TraceEvent[]): StepThink[] {
  const buckets: Bucket[] = [];
  const open = new Map<string, Bucket>();
  const lastToolId = new Map<string, string>();
  let n = 0;

  const ensure = (agentId: string): Bucket => {
    const cur = open.get(agentId);
    if (cur && !cur.closed) return cur;
    const b: Bucket = {
      id: `think-${agentId}-${++n}`,
      agentId,
      raw: "",
      closed: false,
    };
    buckets.push(b);
    open.set(agentId, b);
    return b;
  };

  const bindAndClose = (agentId: string, stepId?: string) => {
    const b = open.get(agentId);
    if (!b || b.closed) return;
    if (stepId) b.stepId = stepId;
    else b.stepId = b.stepId || lastToolId.get(agentId);
    b.closed = true;
  };

  for (const ev of trace) {
    if (ev.type === "step.delta") {
      const agent = String(ev.payload.agent_id ?? "single_agent") || "single_agent";
      ensure(agent).raw += String(ev.payload.delta ?? "");
    } else if (ev.type === "tool.start" || ev.type === "tool.confirm_request") {
      const agent = String(ev.payload.agent_id ?? "").trim() || "single_agent";
      const callId = String(ev.payload.call_id ?? ev.payload.id ?? "").trim();
      if (callId) lastToolId.set(agent, callId);
      bindAndClose(agent, callId || undefined);
    } else if (ev.type === "agent.deactivate") {
      bindAndClose(String(ev.payload.agent_id ?? ""));
    } else if (ev.type === "graph.end") {
      for (const agent of [...open.keys()]) bindAndClose(agent);
    }
  }

  return buckets.map(toThink).filter((t): t is StepThink => Boolean(t));
}

/** Put each think under the work-log row it belongs to. Never dump all at the top. */
export function assignThinksToSteps(
  thinks: StepThink[],
  steps: Array<{ id: string; agentId?: string; kind?: string }>,
): { byStep: Map<string, StepThink[]>; leftover: StepThink[] } {
  const byStep = new Map<string, StepThink[]>();
  const used = new Set<string>();
  const workSteps = steps.filter((s) => s.kind !== "file" && s.kind !== "prep");

  const push = (stepId: string, t: StepThink) => {
    const arr = byStep.get(stepId) ?? [];
    arr.push(t);
    byStep.set(stepId, arr);
    used.add(t.id);
  };

  for (const t of thinks) {
    if (!t.stepId) continue;
    const hit = workSteps.find((s) => s.id === t.stepId);
    if (hit) push(hit.id, t);
  }

  const lastByAgent = new Map<string, string>();
  for (const s of workSteps) {
    if (s.agentId) lastByAgent.set(s.agentId, s.id);
  }
  const lastAny = workSteps.at(-1)?.id;

  for (const t of thinks) {
    if (used.has(t.id)) continue;
    const host =
      (t.agentId && lastByAgent.get(t.agentId)) || lastAny;
    if (host) push(host, t);
  }

  const leftover = thinks.filter((t) => !used.has(t.id));
  return { byStep, leftover };
}
