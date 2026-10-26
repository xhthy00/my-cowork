/** @vitest-environment jsdom */
import { beforeEach, expect, it, vi } from "vitest";
import { refreshIndustryApps, useIndustryApps } from "../../renderer/src/store/industryApps";

beforeEach(() => useIndustryApps.setState(useIndustryApps.getInitialState()));

it("shares concurrent catalog reads", async () => {
  const industryList = vi.fn().mockResolvedValue({ apps: [] });
  window.api = { ...window.api, industryList };
  const first = refreshIndustryApps();
  expect(refreshIndustryApps()).toBe(first);
  await first;
  expect(industryList).toHaveBeenCalledOnce();
  expect(useIndustryApps.getState().loading).toBe(false);
});

it("does not let an older read overwrite a refresh after a runtime change", async () => {
  let finishOld!: (result: any) => void;
  const industryList = vi.fn()
    .mockReturnValueOnce(new Promise(resolve => { finishOld = resolve; }))
    .mockResolvedValueOnce({ apps: [], lifecycle: { busy: false, phase: "committed", generation: "new" } });
  window.api = { ...window.api, industryList };
  const old = refreshIndustryApps();
  await Promise.resolve();
  await refreshIndustryApps(true);
  finishOld({ apps: [{ id: "cn.removed.app" }] });
  expect(await old).toBeUndefined();
  expect(useIndustryApps.getState().catalog?.apps).toEqual([]);
  expect(useIndustryApps.getState().catalog?.lifecycle?.generation).toBe("new");
  expect(useIndustryApps.getState().loading).toBe(false);
});
