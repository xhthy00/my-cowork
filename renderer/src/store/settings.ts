import { create } from "zustand";
import { persist } from "zustand/middleware";

import {
  applyDocumentAppearance,
  type Appearance,
} from "../lib/appearance";

export type { Appearance };

export interface SettingsState {
  whitelist: string[];
  apiKey: string;
  appearance: Appearance;
  setWhitelist: (paths: string[]) => void;
  setApiKey: (key: string) => void;
  setAppearance: (appearance: Appearance) => void;
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      whitelist: ["~/Desktop", "~/Documents", "~/Downloads"],
      apiKey: "",
      appearance: "system",
      setWhitelist: (paths) => set({ whitelist: paths }),
      setApiKey: (key) => set({ apiKey: key }),
      setAppearance: (appearance) => {
        applyDocumentAppearance(appearance);
        set({ appearance });
      },
    }),
    {
      name: "my-cowork-settings",
      partialize: (s) => ({ appearance: s.appearance }),
      onRehydrateStorage: () => (state) => {
        if (state?.appearance) applyDocumentAppearance(state.appearance);
      },
    },
  ),
);
