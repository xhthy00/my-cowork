import { describe, expect, it } from "vitest";

import {
  reconcileToolkitState,
  TOOLKIT_MIN_DISPLAY_MS,
} from "../../renderer/src/components/session/AgentPoolSection";

type State = Parameters<typeof reconcileToolkitState>[0];

function makeState(): State {
  return { entries: new Map(), timers: new Map(), retired: new Set() };
}

function makeScheduler() {
  const scheduled: Array<{ id: string; delay: number; handle: number }> = [];
  let nextHandle = 1;
  const schedule = (id: string, delay: number) => {
    const handle = nextHandle++;
    scheduled.push({ id, delay, handle });
    return handle as unknown as ReturnType<typeof setTimeout>;
  };
  const cancel = (_h: ReturnType<typeof setTimeout>) => {};
  return { scheduled, schedule, cancel };
}

describe("reconcileToolkitState (Eigent Agent Pool)", () => {
  it("shows a RUNNING toolkit immediately", () => {
    const state = makeState();
    const { schedule, cancel } = makeScheduler();
    const names = reconcileToolkitState(
      state,
      [{ id: "a1", name: "Browser Toolkit", status: "running" }],
      {
        now: 0,
        minDisplayMs: TOOLKIT_MIN_DISPLAY_MS,
        schedule,
        cancel,
      },
    );
    expect(names).toEqual(["Browser Toolkit"]);
  });

  it("keeps completed toolkit visible until minDisplayMs", () => {
    const state = makeState();
    const { schedule, cancel } = makeScheduler();
    reconcileToolkitState(
      state,
      [{ id: "a1", name: "Browser Toolkit", status: "running" }],
      { now: 0, minDisplayMs: 1500, schedule, cancel },
    );
    const names = reconcileToolkitState(
      state,
      [{ id: "a1", name: "Browser Toolkit", status: "completed" }],
      { now: 50, minDisplayMs: 1500, schedule, cancel },
    );
    expect(names).toEqual(["Browser Toolkit"]);
  });
});
