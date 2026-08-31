/**
 * Agent thinking process display.
 * Ported from AionUi ThoughtDisplay, with thinking-orbs for live status.
 */
import { ThinkingOrb, type OrbState } from "thinking-orbs";
import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";

export interface ThoughtData {
  subject: string;
  description: string;
}

type ThoughtDisplayProps = {
  thought?: ThoughtData | null;
  style?: "default" | "compact";
  running?: boolean;
  statusText?: string;
  onStop?: () => void;
  onRetryStart?: () => void;
  startedAtMs?: number | null;
  externalElapsedSource?: boolean;
};

const BASE_CLASS =
  "relative z-[1] mb-2 px-[10px] py-[10px] rounded-2xl bg-ds-bg-neutral-default-default text-[14px] leading-[20px] text-ds-text-neutral-default-default";

/** Map live thought copy to a thinking-orbs verb. */
export function orbStateFromSubject(subject?: string | null): OrbState {
  const t = (subject ?? "").toLowerCase();
  if (/search|搜|检索|浏览|browser|fetch|抓取|读取网页/.test(t)) return "searching";
  if (/生成回答|撰写|草稿|composing|正在写|正在组装|正在写入/.test(t)) return "composing";
  if (/完成|solve|校验/.test(t)) return "solving";
  if (/连接|mcp|connect|配对/.test(t)) return "connecting";
  if (/plan|拆解|规划|todo|编织/.test(t)) return "weaving";
  if (/执行|tool|bash|write|正在执行/.test(t)) return "working";
  if (/分析|开始|listen|听取/.test(t)) return "searching";
  if (/运行中/.test(t)) return "working";
  return "breathing";
}

const ThoughtDisplay = ({
  thought,
  style = "default",
  running = false,
  statusText,
  onStop: _onStop,
  onRetryStart,
  startedAtMs,
  externalElapsedSource,
}: ThoughtDisplayProps) => {
  const formatElapsedTime = (seconds: number): string => {
    const sUnit = "s";
    const mUnit = "m";

    if (seconds < 60) {
      return `${seconds}${sUnit}`;
    }
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}${mUnit} ${remainingSeconds}${sUnit}`;
  };

  const [elapsedTime, setElapsedTime] = useState(0);
  const startTimeRef = useRef<number>(Date.now());

  const hasValidStartedAt =
    externalElapsedSource === true &&
    typeof startedAtMs === "number" &&
    Number.isFinite(startedAtMs) &&
    startedAtMs > 0;
  const suppressElapsed = externalElapsedSource === true && !hasValidStartedAt;
  const showElapsed = running && !suppressElapsed;
  const orbState = orbStateFromSubject(thought?.subject ?? statusText);

  useEffect(() => {
    if (
      externalElapsedSource === true &&
      typeof startedAtMs === "number" &&
      Number.isFinite(startedAtMs) &&
      startedAtMs > 0
    ) {
      const tick = () => setElapsedTime(Math.max(0, Math.floor((Date.now() - startedAtMs) / 1000)));
      tick();
      const timer = setInterval(tick, 1000);
      return () => clearInterval(timer);
    }

    if (externalElapsedSource === true) {
      setElapsedTime(0);
      return;
    }

    if (!running && !thought?.subject) {
      setElapsedTime(0);
      return;
    }

    startTimeRef.current = Date.now();
    setElapsedTime(0);

    const timer = setInterval(() => {
      const elapsed = Math.floor((Date.now() - startTimeRef.current) / 1000);
      setElapsedTime(elapsed);
    }, 1000);

    return () => clearInterval(timer);
  }, [externalElapsedSource, startedAtMs, running, thought?.subject]);

  const containerStyle =
    style === "compact"
      ? { maxHeight: "100px", overflow: "scroll" as const, marginBottom: "8px" }
      : undefined;

  if (!thought?.subject && !running && !statusText) {
    return null;
  }

  const orb = (running || Boolean(thought?.subject)) && (
    <ThinkingOrb
      state={orbState}
      size={20}
      theme="auto"
      paused={!running}
      aria-label={thought?.subject || statusText || "思考中"}
      className="shrink-0"
    />
  );

  if (!thought?.subject && (running || statusText)) {
    return (
      <div className={cn(BASE_CLASS, "flex items-center gap-[8px]")} style={containerStyle}>
        {orb}
        <span className="min-w-0 flex-1 truncate text-ds-text-neutral-muted-default" title={statusText}>
          {statusText ?? "正在处理"}
          {showElapsed && <span className="ml-[8px] opacity-60">({formatElapsedTime(elapsedTime)})</span>}
        </span>
        {onRetryStart && (
          <button
            type="button"
            className="shrink-0 cursor-pointer text-[12px] text-ds-text-information-default-default hover:opacity-80"
            onClick={onRetryStart}
          >
            重新开始
          </button>
        )}
      </div>
    );
  }

  const showDescription = thought?.description && thought.description !== thought.subject;

  return (
    <div className={cn(BASE_CLASS, "flex items-center gap-[8px]")} style={containerStyle}>
      {orb}
      <div className="flex min-w-0 flex-1 items-center gap-[8px]">
        <span className="inline-flex h-[20px] shrink-0 items-center whitespace-nowrap rounded-sm bg-ds-bg-neutral-subtle-default px-[8px] text-[12px] leading-none text-ds-text-information-default-default">
          {thought?.subject}
        </span>
        {showDescription && (
          <span className="min-w-0 flex-1 truncate" title={thought?.description}>
            {thought?.description}
          </span>
        )}
        {showElapsed && (
          <span className="whitespace-nowrap text-[12px] text-ds-text-neutral-subtle-default">
            ({formatElapsedTime(elapsedTime)})
          </span>
        )}
      </div>
    </div>
  );
};

export default ThoughtDisplay;
