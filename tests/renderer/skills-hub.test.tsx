/**
 * @vitest-environment jsdom
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SkillHubSuite from "../../renderer/src/components/skills/SkillHubSuite";
import { formatCount } from "../../renderer/src/components/skills/SkillHubCard";

const BACKEND_URL = "http://127.0.0.1:8000";

const HUB_SKILL = {
  name: "编程专家.Skill",
  description: "编程助手",
  iconUrl: null,
  downloads: 435385,
  stars: 26,
  category: "dev-programming",
  slug: "dev-expert",
  handle: "user_741dc82b",
  version: "1.0.48",
  requiresApiKey: false,
  homepage: "https://api.skillhub.cn/user_741dc82b/dev-expert",
};

describe("SkillHubSuite", () => {
  let originalFetch: typeof fetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn(async (input, init) => {
      const url = String(input);
      if (url.includes("/api/skillhub/install") && init?.method === "POST") {
        return {
          ok: true,
          status: 200,
          json: async () => ({ id: "dev-expert", name: "编程专家.Skill" }),
        } as Response;
      }
      if (url.includes("/api/skillhub")) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ skills: [HUB_SKILL], total: 1 }),
        } as Response;
      }
      return { ok: true, status: 200, json: async () => ({}) } as Response;
    }) as unknown as typeof fetch;
    window.api = {
      ...window.api,
      getBackendUrl: vi.fn().mockResolvedValue(BACKEND_URL),
    };
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("formats download counts like WorkBuddy", () => {
    expect(formatCount(435385)).toBe("435k");
    expect(formatCount(26)).toBe("26");
  });

  it("loads hub skills then sends category on chip click", async () => {
    render(
      <SkillHubSuite installedIds={new Set()} onInstalled={() => {}} />,
    );

    await waitFor(() => {
      expect(screen.getByText("编程专家.Skill")).toBeInTheDocument();
    });
    const first = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.find((c) =>
      String(c[0]).includes("/api/skillhub?"),
    );
    expect(String(first?.[0])).toContain("sortBy=score");
    expect(String(first?.[0])).not.toContain("category=");

    await userEvent.click(screen.getByRole("button", { name: "开发编程" }));

    await waitFor(() => {
      const calls = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.filter((c) =>
        String(c[0]).includes("/api/skillhub?"),
      );
      expect(calls.some((c) => String(c[0]).includes("category=dev-programming"))).toBe(true);
    });
  });

  it("POSTs install when clicking plus", async () => {
    const onInstalled = vi.fn();
    render(
      <SkillHubSuite installedIds={new Set()} onInstalled={onInstalled} />,
    );
    await waitFor(() => {
      expect(screen.getByLabelText("安装 编程专家.Skill")).toBeInTheDocument();
    });

    await userEvent.click(screen.getByLabelText("安装 编程专家.Skill"));

    await waitFor(() => {
      const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.find((c) =>
        String(c[0]).includes("/api/skillhub/install"),
      );
      expect(call).toBeTruthy();
      expect(call?.[1]).toMatchObject({ method: "POST" });
      expect(JSON.parse(String(call?.[1]?.body))).toEqual({
        handle: "user_741dc82b",
        slug: "dev-expert",
      });
      expect(onInstalled).toHaveBeenCalled();
    });
  });

  it("renders hub icon urls", async () => {
    const withIcon = {
      ...HUB_SKILL,
      iconUrl: "https://cloudcache.tencent-cloud.com/icon.png",
    };
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ skills: [withIcon], total: 1 }),
    })) as unknown as typeof fetch;
    render(
      <SkillHubSuite installedIds={new Set()} onInstalled={() => {}} />,
    );
    await waitFor(() => {
      const img = document.querySelector(`img[src="${withIcon.iconUrl}"]`);
      expect(img).toBeTruthy();
    expect(img).toHaveAttribute("referrerpolicy", "no-referrer");
    });
  });

  it("sends keyword when searching SkillHub", async () => {
    render(<SkillHubSuite installedIds={new Set()} onInstalled={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText("编程专家.Skill")).toBeInTheDocument();
    });
    await userEvent.type(screen.getByPlaceholderText("搜索 SkillHub 技能…"), "pdf");
    await userEvent.keyboard("{Enter}");
    await waitFor(() => {
      const calls = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.filter((c) =>
        String(c[0]).includes("/api/skillhub?"),
      );
      expect(calls.some((c) => String(c[0]).includes("keyword=pdf"))).toBe(true);
    });
  });
});
