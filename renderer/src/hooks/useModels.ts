import { useCallback, useEffect, useState } from "react";

import type { ModelsState } from "../window";

const EMPTY: ModelsState = { profiles: [], activeId: null };

export function useModels() {
  const [models, setModels] = useState<ModelsState>(EMPTY);
  const [switching, setSwitching] = useState(false);
  const [status, setStatus] = useState("");

  const refresh = useCallback(() => {
    if (!window.api?.getModels) return;
    void window.api.getModels().then(setModels).catch(() => undefined);
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const setActive = useCallback(async (id: string) => {
    if (!id || !window.api?.setActiveModel) return;
    setSwitching(true);
    setStatus("正在切换模型…");
    try {
      const next = await window.api.setActiveModel(id);
      setModels(next);
      setStatus("");
    } catch (err) {
      setStatus(err instanceof Error ? err.message : String(err));
    } finally {
      setSwitching(false);
    }
  }, []);

  const active = models.profiles.find((p) => p.id === models.activeId) ?? null;

  return {
    models,
    active,
    refresh,
    setActive,
    switching,
    status,
  };
}

export function navigateToModelsConfig() {
  window.dispatchEvent(new CustomEvent("my-cowork:navigate", { detail: "models" }));
}
