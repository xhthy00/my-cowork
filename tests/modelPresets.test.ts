import { describe, expect, it } from "vitest";

import {
  findPreset,
  profileForPreset,
  resolvePresetId,
} from "../renderer/src/lib/modelPresets";

describe("profileForPreset", () => {
  it("matches legacy Minimax on China host without presetId", () => {
    const preset = findPreset("minimax")!;
    const profiles = [
      {
        id: "m1",
        name: "Minimax",
        provider: "openai_compat",
        model: "MiniMax-M3",
        baseUrl: "https://api.minimaxi.com/v1",
      },
    ];
    const hit = profileForPreset(profiles, preset);
    expect(hit?.id).toBe("m1");
    expect(resolvePresetId(profiles[0]!)).toBe("minimax");
  });

  it("matches by name when host differs slightly", () => {
    const preset = findPreset("minimax")!;
    const profiles = [
      {
        id: "m2",
        name: "Minimax",
        provider: "openai_compat",
        model: "x",
        baseUrl: "https://example.com/v1",
      },
    ];
    expect(profileForPreset(profiles, preset)?.id).toBe("m2");
  });
});
