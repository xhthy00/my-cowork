import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export type ConfigCardRingStatus = "idle" | "configuring" | "success" | "error";

const RING_INSET = "-1px";

const BORDER_COLOR: Record<Exclude<ConfigCardRingStatus, "idle">, string> = {
  configuring: "var(--ds-border-neutral-subtle-disabled)",
  success: "var(--ds-text-success-default-default, #00a63e)",
  error: "var(--ds-text-error-default-default, #e7000b)",
};

const CONFIGURING_TRANSITION = {
  transform: {
    duration: 1.2,
    repeat: Infinity,
    ease: "linear" as const,
  },
  opacity: {
    duration: 1.2,
    repeat: Infinity,
    ease: "linear" as const,
  },
};

const SUCCESS_TRANSITION = {
  duration: 0.24,
  ease: [0.23, 1, 0.32, 1] as const,
};

const ERROR_TRANSITION = {
  duration: 0.28,
  ease: [0.23, 1, 0.32, 1] as const,
};

function getRingMotionProps(status: Exclude<ConfigCardRingStatus, "idle">) {
  switch (status) {
    case "configuring":
      return {
        animate: {
          transform: ["scale(1)", "scale(1.01)", "scale(1)"],
          opacity: [0.7, 1, 0.7],
        },
        transition: CONFIGURING_TRANSITION,
      };
    case "success":
      return {
        animate: {
          transform: "scale(1)",
          opacity: 1,
        },
        transition: SUCCESS_TRANSITION,
      };
    case "error":
      return {
        animate: {
          transform: ["scale(1)", "scale(1.01)", "scale(1)"],
          opacity: [1, 0.2, 1],
        },
        transition: ERROR_TRANSITION,
      };
  }
}

export function ConfigModelCard({
  status,
  children,
  className,
}: {
  status: ConfigCardRingStatus;
  children: ReactNode;
  className?: string;
}) {
  const shouldReduceMotion = useReducedMotion();
  const showRing = status !== "idle";

  const ringMotion = showRing
    ? shouldReduceMotion
      ? {
          animate: { transform: "scale(1)", opacity: 1 },
          transition: { duration: 0.2, ease: [0.23, 1, 0.32, 1] as const },
        }
      : getRingMotionProps(status)
    : null;
  const ringColor = status === "idle" ? undefined : BORDER_COLOR[status];

  return (
    <div className={cn("relative w-full", className)}>
      <AnimatePresence>
        {ringMotion && (
          <motion.div
            key="config-card-ring"
            className="pointer-events-none absolute z-0 rounded-2xl border-2 border-solid"
            style={{ inset: RING_INSET, borderColor: ringColor }}
            initial={{
              transform: "scale(1)",
              opacity: 0,
            }}
            animate={ringMotion.animate}
            exit={{ opacity: 0, transition: { duration: 0.2 } }}
            transition={ringMotion.transition}
          />
        )}
      </AnimatePresence>
      <div className="relative z-[1] flex w-full flex-col rounded-2xl bg-ds-bg-neutral-subtle-default">
        {children}
      </div>
    </div>
  );
}
