import { useMemo, useState } from "react";

import TraceTree from "./trace/TraceTree";
import { useSessionStore, type TraceEvent } from "../store/session";

interface TracePanelProps {
  /** When false, hide the panel (standalone mode). Embedded mode ignores this. */
  isTraceOpen?: boolean;
  /** Render inside SessionSidePanel accordion without outer chrome. */
  embedded?: boolean;
}

interface LiveStep {
  id: string;
  name: string;
  status: "done" | "active" | "pending" | "error";
  detail?: string;
  open: boolean;
}

const NODE_LABEL: Record<string, string> = {
  supervisor: "意图理解",
  single_agent: "单智能体",
  developer_agent: "开发智能体 · 文件/终端",
  browser_agent: "浏览器智能体 · 网页/检索",
  document_agent: "文档智能体 · 文档生成",
  multi_modal_agent: "多模态智能体 · 产物协同",
  coordinator: "任务协调",
  file_worker: "开发智能体 · 文件/终端",
  doc_worker: "文档智能体 · 文档生成",
  web_worker: "浏览器智能体 · 网页/检索",
  msg_worker: "多模态智能体 · 产物协同",
};

function formatDetail(payload: Record<string, unknown>): string {
  try {
    return JSON.stringify(payload, null, 2);
  } catch {
    return String(payload);
  }
}

function buildLiveSteps(
  trace: TraceEvent[],
  pendingConfirmIds: Set<string>,
): LiveStep[] {
  const steps: LiveStep[] = [];
  let ended = false;
  let endError = false;

  for (const ev of trace) {
    if (ev.type === "graph.step" || ev.type === "step.start") {
      const node = String(ev.payload.node ?? "step");
      steps.push({
        id: ev.id,
        name: NODE_LABEL[node] ?? `${node} · 执行`,
        status: "done",
        detail: formatDetail(ev.payload),
        open: false,
      });
    } else if (ev.type === "tool.confirm_request") {
      const callId = String(ev.payload.call_id ?? "");
      const tool = String(ev.payload.tool ?? "tool");
      const waiting = pendingConfirmIds.has(callId);
      steps.push({
        id: ev.id,
        name: `confirm · ${tool}`,
        status: waiting ? "active" : "done",
        detail: formatDetail(ev.payload),
        open: waiting,
      });
    } else if (ev.type === "tool.result") {
      const tool = String(ev.payload.tool ?? "tool");
      steps.push({
        id: ev.id,
        name: `${tool} · 结果`,
        status: "done",
        detail: formatDetail(ev.payload),
        open: false,
      });
    } else if (ev.type === "graph.end") {
      ended = true;
      endError = ev.payload.status === "error";
      steps.push({
        id: ev.id,
        name: endError ? "graph · 失败" : "graph · 完成",
        status: endError ? "error" : "done",
        detail: formatDetail(ev.payload),
        open: endError,
      });
    }
  }

  if (!ended && steps.length > 0) {
    const last = steps[steps.length - 1];
    // Don't fake "waiting for confirm" for already-resolved confirm steps.
    if (last.status === "done" && !last.name.startsWith("confirm")) {
      last.status = "active";
      last.open = true;
    }
  }

  return steps;
}

export default function TracePanel({
  isTraceOpen = true,
  embedded = false,
}: TracePanelProps) {
  const [activeTab, setActiveTab] = useState<"steps" | "graph" | "logs">("steps");
  const [openIds, setOpenIds] = useState<Record<string, boolean>>({});
  const trace = useSessionStore((s) => s.trace);
  const traceNodes = useSessionStore((s) => s.traceNodes);
  const traceEdges = useSessionStore((s) => s.traceEdges);
  const confirmQueue = useSessionStore((s) => s.confirmQueue);

  const pendingConfirmIds = useMemo(
    () => new Set(confirmQueue.map((c) => c.call_id)),
    [confirmQueue],
  );

  const steps = useMemo(
    () => buildLiveSteps(trace, pendingConfirmIds),
    [trace, pendingConfirmIds],
  );

  const stepCount = steps.filter((s) => s.name.includes("·")).length;
  const eventCount = trace.length;

  const budget = useMemo(() => {
    let tokens = 0;
    let maxTokens = 200_000;
    let exhausted = false;
    let dailyAlert: string | null = null;
    for (const ev of trace) {
      if (ev.type === "budget.update") {
        tokens = Number(ev.payload.tokens ?? tokens);
        maxTokens = Number(ev.payload.max_tokens ?? maxTokens);
      }
      if (ev.type === "budget.exhausted") {
        exhausted = true;
        tokens = Number(ev.payload.tokens ?? tokens);
        maxTokens = Number(ev.payload.max_tokens ?? maxTokens);
      }
      if (ev.type === "metrics.daily_exceeded") {
        const usd = Number(ev.payload.usd ?? 0);
        const limit = Number(ev.payload.limit_usd ?? 0);
        dailyAlert = `今日成本 $${usd.toFixed(2)} 已超阈值 $${limit.toFixed(2)}`;
      }
    }
    const pct = maxTokens > 0 ? Math.min(100, Math.round((tokens / maxTokens) * 100)) : 0;
    const usd = tokens * 1e-6;
    return { tokens, maxTokens, pct, usd, exhausted, dailyAlert };
  }, [trace]);

  function toggle(id: string, fallbackOpen: boolean) {
    setOpenIds((prev) => ({
      ...prev,
      [id]: !(prev[id] ?? fallbackOpen),
    }));
  }

  const body = (
    <>
      <div className={embedded ? "mb-2 flex flex-wrap gap-1" : "trace-tabs"}>
        {[
          { id: "steps", label: "步骤" },
          { id: "graph", label: "图" },
          { id: "logs", label: "日志" },
        ].map((tab) => (
          <button
            key={tab.id}
            className={
              embedded
                ? `rounded-md px-2 py-1 text-xs ${
                    activeTab === tab.id
                      ? "bg-ds-bg-neutral-subtle-default font-medium"
                      : "text-ds-text-neutral-muted-default"
                  }`
                : `trace-tab ${activeTab === tab.id ? "active" : ""}`
            }
            type="button"
            onClick={() => setActiveTab(tab.id as typeof activeTab)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div
        className={
          embedded ? "flex max-h-72 flex-col gap-2 overflow-y-auto" : "trace-body"
        }
      >
        <div
          className={
            embedded
              ? "rounded-lg border border-ds-border-neutral-subtle-disabled px-2 py-1.5 text-xs"
              : "usage-card"
          }
        >
          <div className={embedded ? "flex justify-between gap-2" : "usage-row"}>
            <span className={embedded ? "text-ds-text-neutral-muted-default" : "label"}>
              Token
            </span>
            <span className={embedded ? "font-medium" : "value"}>
              {budget.tokens.toLocaleString()}
            </span>
          </div>
          {!embedded && (
            <>
              <div className="usage-row">
                <span className="label">预估成本</span>
                <span className="value cost">${budget.usd.toFixed(4)}</span>
              </div>
              <div className="usage-bar">
                <div style={{ width: `${budget.pct}%` }} />
              </div>
            </>
          )}
          <div
            className={
              embedded ? "mt-1 text-ds-text-neutral-subtle-default" : "usage-cap"
            }
          >
            预算 {(budget.maxTokens / 1000).toFixed(0)}k · {budget.pct}% · 事件{" "}
            {eventCount} · 步骤 {stepCount}
            {budget.exhausted ? " · 已截断" : ""}
          </div>
          {budget.dailyAlert && (
            <div
              className={embedded ? "mt-1 text-amber-600" : "usage-cap"}
              style={
                embedded ? undefined : { color: "var(--warning)", marginTop: 6 }
              }
            >
              {budget.dailyAlert}
            </div>
          )}
        </div>

        {activeTab === "steps" && (
          <div id="tab-steps">
            {steps.length === 0 && (
              <div
                className={
                  embedded
                    ? "px-1 py-1 text-body-sm text-ds-text-neutral-subtle-default opacity-60"
                    : "trace-empty"
                }
              >
                发送任务后，这里会显示实时执行步骤
              </div>
            )}
            {steps.map((step, index) => {
              const isOpen = openIds[step.id] ?? step.open;
              return (
                <div
                  key={step.id}
                  className={
                    embedded
                      ? "mb-1 rounded-md border border-ds-border-neutral-subtle-disabled"
                      : `step ${step.status} ${isOpen ? "open" : ""}`
                  }
                >
                  <button
                    className={
                      embedded
                        ? "flex w-full items-center gap-2 px-2 py-1.5 text-left text-xs"
                        : "step-head"
                    }
                    type="button"
                    onClick={() => toggle(step.id, step.open)}
                  >
                    <span className={embedded ? "opacity-60" : "step-num"}>
                      {index + 1}
                    </span>
                    <span className="min-w-0 truncate">{step.name}</span>
                  </button>
                  {isOpen && (
                    <div
                      className={
                        embedded
                          ? "border-t border-ds-border-neutral-subtle-disabled px-2 py-1.5 text-[11px] text-ds-text-neutral-muted-default"
                          : "step-body"
                      }
                    >
                      {step.status === "active" && step.name.startsWith("confirm")
                        ? "等待用户确认"
                        : step.status === "error"
                          ? "步骤失败"
                          : step.status === "active"
                            ? "执行中…"
                            : "步骤已完成"}
                      {step.detail && (
                        <div className="mt-1 max-h-24 overflow-auto font-mono text-[10px] opacity-80">
                          {step.detail}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {activeTab === "graph" && (
          <div id="tab-graph" className={embedded ? "h-48" : undefined}>
            {traceNodes.length === 0 ? (
              <div
                className={
                  embedded
                    ? "px-1 py-1 text-body-sm text-ds-text-neutral-subtle-default opacity-60"
                    : "trace-empty"
                }
              >
                暂无 Graph 节点
              </div>
            ) : (
              <TraceTree nodes={traceNodes} edges={traceEdges} />
            )}
          </div>
        )}

        {activeTab === "logs" && (
          <div id="tab-logs">
            {trace.length === 0 ? (
              <div
                className={
                  embedded
                    ? "px-1 py-1 text-body-sm text-ds-text-neutral-subtle-default opacity-60"
                    : "trace-empty"
                }
              >
                暂无日志
              </div>
            ) : (
              <div className="font-mono text-[11px] leading-relaxed">
                {trace.map((ev) => {
                  const node = ev.payload.node
                    ? ` node=${String(ev.payload.node)}`
                    : "";
                  const tool = ev.payload.tool
                    ? ` ${String(ev.payload.tool)}`
                    : "";
                  const status = ev.payload.status
                    ? ` status=${String(ev.payload.status)}`
                    : "";
                  return (
                    <div key={ev.id}>
                      {ev.type}
                      {node}
                      {tool}
                      {status}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </>
  );

  if (embedded) {
    return <div className="trace-embedded min-w-0">{body}</div>;
  }

  return (
    <aside className={`trace ${isTraceOpen ? "" : "hidden"}`}>
      <div className="trace-head">
        <h2>执行轨迹</h2>
        <button className="icon-btn" type="button" title="收起">
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            width="16"
            height="16"
          >
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>
      {body}
    </aside>
  );
}
