import { describe, expect, it } from "vitest";
import {
  capabilityFor,
  runtimeCapability,
  type ModelCatalog,
} from "../electron/model_capabilities";
const catalog: ModelCatalog = {
  updatedAt: "test",
  models: [
    {
      id: "deepseek/ds",
      provider: "deepseek",
      model: "ds",
      name: "DS",
      reasoning: true,
      options: [{ type: "effort", values: ["low", "high"] }],
      context: 1000000,
      output: 64000,
    },
  ],
};
const profile = {
  id: "p",
  name: "test",
  provider: "openai_compat" as const,
  model: "ds",
  baseUrl: "https://api.deepseek.com",
};
describe("capability resolution", () => {
  it("matches exact model and host, never a misleading proxy domain", () => {
    expect(capabilityFor(profile, catalog)?.id).toBe("deepseek/ds");
    expect(
      capabilityFor(
        { ...profile, baseUrl: "https://api.deepseek.com.example.org" },
        catalog,
      ),
    ).toBeUndefined();
    expect(
      capabilityFor({ ...profile, model: "ds-new" }, catalog),
    ).toBeUndefined();
  });
  it("preserves alias and rejects unsupported effort without silently dropping it", () => {
    const alias = {
      ...profile,
      model: "company-alias",
      capabilityId: "deepseek/ds",
      reasoning: { effort: "high" },
    };
    expect(runtimeCapability(alias, catalog)).toMatchObject({
      reasoning_mode: "deepseek",
      reasoning_effort: "high",
      context_window: 1000000,
    });
    expect(alias.model).toBe("company-alias");
    expect(() =>
      runtimeCapability({ ...alias, reasoning: { effort: "medium" } }, catalog),
    ).toThrow("不支持");
  });
});

it("allows independent Anthropic effort while thinking is off", () => {
  const cap: ModelCatalog = {
    updatedAt: "test",
    models: [
      {
        id: "anthropic/claude-opus-4-5",
        provider: "anthropic",
        model: "claude-opus-4-5",
        name: "Claude",
        context: 200000,
        output: 64000,
        reasoning: true,
        options: [
          { type: "toggle" },
          { type: "effort", values: ["low", "high"] },
        ],
      },
    ],
  };
  expect(
    runtimeCapability(
      {
        id: "a",
        name: "Claude",
        provider: "anthropic",
        model: "claude-opus-4-5",
        reasoning: { enabled: false, effort: "high" },
      },
      cap,
    ),
  ).toMatchObject({ thinking_enabled: false, reasoning_effort: "high" });
});
