/** @vitest-environment jsdom */
import { fireEvent, render, screen } from "@testing-library/react";
import { it, expect, vi } from "vitest";
import StartupSplash from "../../renderer/src/components/StartupSplash";

it("shows a failure that occurred before subscription and a rejected retry", async () => {
  window.api = {
    getBackendUrl: vi.fn().mockResolvedValue(""),
    getBackendStatus: vi.fn().mockResolvedValue({ state: "failed", error: "启动超时" }),
    restartBackend: vi.fn().mockRejectedValue(new Error("仍然无法启动")),
  } as unknown as typeof window.api;
  render(<StartupSplash />);
  expect(await screen.findByText("启动超时")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "重试" }));
  expect(await screen.findByText("仍然无法启动")).toBeInTheDocument();
});
