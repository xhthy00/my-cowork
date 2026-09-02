/**
 * Adapted from eigent: src/components/Dashboard/HistoryTabsNav.tsx
 */
import { Blocks, Bot, Compass, Hammer, Library, Settings } from "lucide-react";
import { motion, useReducedMotion } from "framer-motion";
import {
  useCallback,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { cn } from "@/lib/utils";
import type { HubTab } from "@/store/pageTab";

export const HISTORY_TAB_IDS = [
  "home",
  "agents",
  "knowledge",
  "connectors",
  "browser",
  "settings",
] as const;

export type HistoryTabId = (typeof HISTORY_TAB_IDS)[number];

const LABELS: Record<HistoryTabId, string> = {
  home: "主页",
  agents: "智能体",
  knowledge: "知识库",
  connectors: "连接器",
  browser: "浏览器",
  settings: "设置",
};

const ICONS: Record<HistoryTabId, ReactNode> = {
  home: <Blocks className="size-4" />,
  agents: <Bot className="size-4" />,
  knowledge: <Library className="size-4" />,
  connectors: <Hammer className="size-4" />,
  browser: <Compass className="size-4" />,
  settings: <Settings className="size-4" />,
};

type Props = {
  activeTab: HubTab;
  onChange: (tab: HubTab) => void;
  className?: string;
};

export function HistoryTabsNav({ activeTab, onChange, className }: Props) {
  const reduceMotion = useReducedMotion() === true;
  const moveTransition = reduceMotion
    ? { duration: 0 }
    : { type: "spring" as const, stiffness: 420, damping: 34, mass: 0.55 };
  const navRef = useRef<HTMLDivElement>(null);
  const [hoveredTab, setHoveredTab] = useState<HistoryTabId | null>(null);
  const [hoverRect, setHoverRect] = useState({ left: 0, top: 0, width: 0, height: 0 });
  const [activeLine, setActiveLine] = useState({ left: 0, top: 0, width: 0 });

  const updateActiveLine = useCallback(() => {
    const nav = navRef.current;
    if (!nav) return;
    const el = nav.querySelector<HTMLElement>(`[data-history-tab="${activeTab}"]`);
    if (!el) return;
    const r = el.getBoundingClientRect();
    const nr = nav.getBoundingClientRect();
    const gapPx = 8;
    setActiveLine({
      left: r.left - nr.left,
      top: r.bottom - nr.top + gapPx,
      width: r.width,
    });
  }, [activeTab]);

  const updateHoverRect = useCallback((id: HistoryTabId | null) => {
    const nav = navRef.current;
    if (!nav || !id) {
      setHoveredTab(null);
      return;
    }
    const el = nav.querySelector<HTMLElement>(`[data-history-tab="${id}"]`);
    if (!el) return;
    const r = el.getBoundingClientRect();
    const nr = nav.getBoundingClientRect();
    setHoveredTab(id);
    setHoverRect({
      left: r.left - nr.left,
      top: r.top - nr.top,
      width: r.width,
      height: r.height,
    });
  }, []);

  useLayoutEffect(() => {
    updateActiveLine();
    const nav = navRef.current;
    if (!nav) return;
    const ro = new ResizeObserver(updateActiveLine);
    ro.observe(nav);
    window.addEventListener("resize", updateActiveLine);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", updateActiveLine);
    };
  }, [updateActiveLine]);

  return (
    <div
      ref={navRef}
      className={cn("relative flex w-full flex-row items-center gap-1", className)}
      role="tablist"
      onMouseLeave={() => setHoveredTab(null)}
    >
      {hoveredTab && (
        <motion.div
          className="pointer-events-none absolute z-0 rounded-lg bg-ds-bg-neutral-subtle-default"
          initial={false}
          animate={hoverRect}
          transition={moveTransition}
        />
      )}
      {HISTORY_TAB_IDS.map((id) => {
        const active = activeTab === id;
        return (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={active}
            data-history-tab={id}
            className={cn(
              "group relative z-10 inline-flex h-8 min-h-8 shrink-0 items-center gap-1 rounded-lg px-2 text-label-sm font-bold transition-colors",
              active
                ? "text-ds-text-neutral-default-default"
                : "text-ds-text-neutral-muted-default hover:text-ds-text-neutral-default-default",
            )}
            onClick={() => onChange(id)}
            onMouseEnter={() => updateHoverRect(id)}
          >
            <span className="inline-flex size-4 shrink-0 items-center justify-center [&_svg]:size-4">
              {ICONS[id]}
            </span>
            {LABELS[id]}
          </button>
        );
      })}
      <motion.div
        className="pointer-events-none absolute z-10 h-0.5 rounded-full bg-ds-bg-brand-default-default"
        initial={false}
        animate={{ left: activeLine.left, top: activeLine.top, width: activeLine.width }}
        transition={moveTransition}
      />
    </div>
  );
}
