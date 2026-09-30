import { useCallback, useEffect, useState } from "react";

import { useSessionsStore, ensureActiveSession } from "../store/sessions";
import type { ModelsState } from "../window";

const EMPTY: ModelsState = { profiles: [], activeId: null };

export function useModels() {
  const [models, setModels] = useState<ModelsState>(EMPTY);
  const switching = false;
  const projectId = useSessionsStore((s) => s.activeId);
  const projectModelId = useSessionsStore(
    (s) => s.sessions.find((p) => p.id === s.activeId)?.modelProfileId,
  );
  const [status, setStatus] = useState("");

  const refresh = useCallback(() => {
    if (!window.api?.getModels) return;
    void window.api
      .getModels()
      .then(setModels)
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    refresh();
    window.addEventListener("my-cowork:models-changed", refresh);
    return () =>
      window.removeEventListener("my-cowork:models-changed", refresh);
  }, [refresh]);

  const setActive = useCallback(
    async (id: string) => {
      if (!models.profiles.some((p) => p.id === id)) return;
      const projectId = ensureActiveSession();
      useSessionsStore
        .getState()
        .touchSession(projectId, { modelProfileId: id });
      setStatus("");
    },
    [models.profiles],
  );

  const selectedId = projectModelId ?? models.activeId;
  const active = models.profiles.find((p) => p.id === selectedId) ?? null;

  // Pin a conversation's initial model and legacy reasoning defaults once.
  // Later global-default edits must only affect new conversations.
  useEffect(() => {
    const store = useSessionsStore.getState();
    const session = store.sessions.find((p) => p.id === store.activeId);
    if (!session || !active) return;
    if (
      session.modelProfileId &&
      session.modelReasoning?.[active.id] !== undefined
    )
      return;
    store.touchSession(session.id, {
      modelProfileId: session.modelProfileId ?? active.id,
      modelReasoning: {
        ...session.modelReasoning,
        [active.id]:
          session.modelReasoning?.[active.id] ?? active.reasoning ?? {},
      },
    });
  }, [active, projectModelId, projectId]);

  return {
    models: { ...models, activeId: selectedId },
    active,
    refresh,
    setActive,
    switching,
    status,
  };
}

export function navigateToModelsConfig() {
  window.dispatchEvent(
    new CustomEvent("my-cowork:navigate", { detail: "models" }),
  );
}
