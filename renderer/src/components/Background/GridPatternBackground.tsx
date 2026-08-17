/**
 * Adapted from eigent: Background/GridPatternBackground.tsx
 */
import { useId } from "react";

const PATTERN_STEP = 24;

/** Grid overlay for use inside a `relative` container. */
export default function GridPatternBackground() {
  const patternId = `${useId().replace(/:/g, "")}-grid`;

  return (
    <svg
      className="pointer-events-none absolute inset-0 z-0 h-full w-full"
      aria-hidden
    >
      <defs>
        <pattern
          id={patternId}
          width={PATTERN_STEP}
          height={PATTERN_STEP}
          patternUnits="userSpaceOnUse"
        >
          <path
            className="stroke-ds-border-neutral-default-default"
            d={`M ${PATTERN_STEP} 0 L 0 0 0 ${PATTERN_STEP}`}
            fill="none"
            strokeWidth={1}
            opacity={0.08}
          />
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill={`url(#${patternId})`} />
    </svg>
  );
}
