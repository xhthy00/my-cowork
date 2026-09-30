import { useEffect, useState } from "react";

/**
 * Increments each time the backend reports ready (first start, or restart after
 * a model/key change). Hub pages stay mounted while hidden, so a page that
 * loaded while the backend was down must reload when this value changes.
 */
export function useBackendEpoch(): number {
  const [epoch, setEpoch] = useState(0);
  useEffect(
    () => window.api?.onBackendReady?.(() => setEpoch((n) => n + 1)),
    [],
  );
  return epoch;
}
