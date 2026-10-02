import { useEffect, useState } from "react";

/** Keep the navigation available without squeezing the task on narrow windows. */
export function useCompactLayout() {
  const [compact, setCompact] = useState(() => window.matchMedia?.("(max-width: 760px)").matches ?? false);
  useEffect(() => {
    const media = window.matchMedia?.("(max-width: 760px)");
    if (!media) return;
    const update = () => setCompact(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  return compact;
}
