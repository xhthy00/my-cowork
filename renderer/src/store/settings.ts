import { create } from "zustand";
import { persist } from "zustand/middleware";

import {
  applyDocumentAppearance,
  type Appearance,
} from "../lib/appearance";
import {
  applyDocumentFontSize,
  DEFAULT_FONT_SIZE_LEVEL,
  type FontSizeLevel,
} from "../lib/fontSize";

export type { Appearance, FontSizeLevel };

export interface SettingsState {
  whitelist: string[];
  apiKey: string;
  appearance: Appearance;
  fontSize: FontSizeLevel;
  setWhitelist: (paths: string[]) => void;
  setApiKey: (key: string) => void;
  setAppearance: (appearance: Appearance) => void;
  setFontSize: (fontSize: FontSizeLevel) => void;
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      whitelist: ["~/Desktop", "~/Documents", "~/Downloads"],
      apiKey: "",
      appearance: "system",
      fontSize: DEFAULT_FONT_SIZE_LEVEL,
      setWhitelist: (paths) => set({ whitelist: paths }),
      setApiKey: (key) => set({ apiKey: key }),
      setAppearance: (appearance) => {
        applyDocumentAppearance(appearance);
        set({ appearance });
      },
      setFontSize: (fontSize) => {
        applyDocumentFontSize(fontSize);
        set({ fontSize });
      },
    }),
    {
      name: "my-cowork-settings",
      partialize: (s) => ({ appearance: s.appearance, fontSize: s.fontSize }),
      onRehydrateStorage: () => (state) => {
        if (state?.appearance) applyDocumentAppearance(state.appearance);
        if (state?.fontSize !== undefined) applyDocumentFontSize(state.fontSize);
      },
    },
  ),
);
