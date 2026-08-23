/**
 * @vitest-environment jsdom
 */

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import OnboardingHint from "../../renderer/src/components/workspace/OnboardingHint";

const CHECKED_KEY = "my-cowork-workspace-onboarding-checked";
const DISMISS_KEY = "my-cowork-workspace-onboarding-dismissed";

describe("OnboardingHint", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    cleanup();
    localStorage.clear();
  });

  it("shows the first incomplete step on an empty welcome", () => {
    render(<OnboardingHint />);
    expect(screen.getByText("下一步：连接日常工具")).toBeTruthy();
  });

  it("renders nothing after all steps are checked", () => {
    localStorage.setItem(CHECKED_KEY, JSON.stringify([1, 2, 3, 4]));
    const { container } = render(<OnboardingHint />);
    expect(container.firstChild).toBeNull();
  });

  it("hides after dismiss and stays hidden", async () => {
    const user = userEvent.setup();
    const { unmount } = render(<OnboardingHint />);
    await user.click(screen.getByRole("button", { name: "关闭入门提示" }));
    expect(localStorage.getItem(DISMISS_KEY)).toBe("1");
    unmount();
    const { container } = render(<OnboardingHint />);
    expect(container.firstChild).toBeNull();
  });
});
