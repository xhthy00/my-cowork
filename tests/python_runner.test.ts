import { EventEmitter } from "events";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// ── hoisted mocks ──────────────────────────────────────────────────────────
const { spawnMock, spawnSyncMock, getMock } = vi.hoisted(() => ({
  spawnMock: vi.fn(),
  spawnSyncMock: vi.fn(),
  getMock: vi.fn(),
}));

vi.mock("child_process", () => ({ spawn: spawnMock, spawnSync: spawnSyncMock }));
vi.mock("http", () => ({ get: getMock }));

// ── helpers ───────────────────────────────────────────────────────────────
class MockChildProcess extends EventEmitter {
  pid = 123456;
  kill = vi.fn();
  stdin = { write: vi.fn() };
  stdout = new EventEmitter();
  stderr = new EventEmitter();
}

function fakeHealthOk(): any {
  const res = new EventEmitter() as any;
  res.statusCode = 200;
  res.resume = vi.fn();
  setTimeout(() => {
    res.emit("data", Buffer.from("healthy"));
    res.emit("end");
  }, 0);
  return res;
}

// ── import under test ──────────────────────────────────────────────────────
import { start } from "../electron/python_runner";

describe("python_runner", () => {
  beforeEach(() => {
    spawnMock.mockClear();
    getMock.mockClear();
  });

  it("extracts port from stdout and returns backend info", async () => {
    spawnMock.mockReturnValue(new MockChildProcess());

    getMock.mockImplementation((_url: string, cb: any) => {
      const res = fakeHealthOk();
      setTimeout(() => cb(res), 0);
      return Object.assign(new EventEmitter(), { destroy: vi.fn(), setTimeout: vi.fn() });
    });

    const promise = start({ cwd: "/fake/cwd", dev: true });

    const proc = spawnMock.mock.results[0].value as MockChildProcess;
    setTimeout(() => {
      proc.stdout.emit("data", Buffer.from("Listening on 127.0.0.1:54321\n"));
    }, 0);

    const info = await promise;
    expect(info.port).toBe(54321);
    expect(info.url).toBe("http://127.0.0.1:54321");
    expect(info.process).toBeDefined();

    expect(spawnMock).toHaveBeenCalledWith(
      "uv",
      ["run", "--no-sync", "uvicorn", "app.main:app", "--port", "0", "--reload", "--reload-dir", path.join("/fake/cwd", "app")],
      expect.objectContaining({
        cwd: "/fake/cwd",
        env: expect.objectContaining({ PYTHONUNBUFFERED: "1" }),
        detached: process.platform !== "win32",
      }),
    );
  });

  it("passes env overrides through to spawn", async () => {
    spawnMock.mockReturnValue(new MockChildProcess());

    getMock.mockImplementation((_url: string, cb: any) => {
      const res = fakeHealthOk();
      setTimeout(() => cb(res), 0);
      return Object.assign(new EventEmitter(), { destroy: vi.fn(), setTimeout: vi.fn() });
    });

    const promise = start({
      cwd: "/fake/cwd",
      dev: true,
      env: { MY_COWORK_API_KEY: "sk-injected" },
    });

    const proc = spawnMock.mock.results[0].value as MockChildProcess;
    setTimeout(() => {
      proc.stdout.emit("data", Buffer.from("Listening on 127.0.0.1:54321\n"));
    }, 0);

    await promise;

    const spawnOpts = spawnMock.mock.calls[0][2] as { env: Record<string, string> };
    expect(spawnOpts.env.MY_COWORK_API_KEY).toBe("sk-injected");
  });

  it("spawns packaged backend with resources cwd, not asar backend/", async () => {
    const resources = fs.mkdtempSync(path.join(os.tmpdir(), "mycowork-res-"));
    const exeName = process.platform === "win32" ? "python_bin.exe" : "python_bin";
    fs.writeFileSync(path.join(resources, exeName), "");
    const prev = (process as { resourcesPath?: string }).resourcesPath;
    (process as { resourcesPath?: string }).resourcesPath = resources;

    spawnMock.mockReturnValue(new MockChildProcess());
    getMock.mockImplementation((_url: string, cb: (res: unknown) => void) => {
      const res = fakeHealthOk();
      setTimeout(() => cb(res), 0);
      return Object.assign(new EventEmitter(), { destroy: vi.fn(), setTimeout: vi.fn() });
    });

    try {
      const promise = start({
        cwd: path.join(resources, "app.asar", "backend"),
        dev: false,
      });
      const proc = spawnMock.mock.results[0].value as MockChildProcess;
      setTimeout(() => {
        proc.stderr.emit(
          "data",
          Buffer.from("Uvicorn running on http://127.0.0.1:54321\n"),
        );
      }, 0);
      await promise;

      expect(spawnMock.mock.calls[0][0]).toBe(path.join(resources, exeName));
      expect(spawnMock.mock.calls[0][2]).toEqual(
        expect.objectContaining({ cwd: resources }),
      );
      expect(
        (spawnMock.mock.calls[0][2] as { env: Record<string, string> }).env
          .MY_COWORK_EXAMPLE_SKILLS,
      ).toBeUndefined();
    } finally {
      (process as { resourcesPath?: string }).resourcesPath = prev;
      fs.rmSync(resources, { recursive: true, force: true });
    }
  });

  it("points packaged backend at extraResources example-skills", async () => {
    const resources = fs.mkdtempSync(path.join(os.tmpdir(), "mycowork-res-"));
    const exeName = process.platform === "win32" ? "python_bin.exe" : "python_bin";
    fs.writeFileSync(path.join(resources, exeName), "");
    const exampleSkills = path.join(resources, "resources", "example-skills");
    fs.mkdirSync(exampleSkills, { recursive: true });
    const prev = (process as { resourcesPath?: string }).resourcesPath;
    (process as { resourcesPath?: string }).resourcesPath = resources;

    spawnMock.mockReturnValue(new MockChildProcess());
    getMock.mockImplementation((_url: string, cb: (res: unknown) => void) => {
      const res = fakeHealthOk();
      setTimeout(() => cb(res), 0);
      return Object.assign(new EventEmitter(), { destroy: vi.fn(), setTimeout: vi.fn() });
    });

    try {
      const promise = start({ cwd: resources, dev: false });
      const proc = spawnMock.mock.results[0].value as MockChildProcess;
      setTimeout(() => {
        proc.stderr.emit(
          "data",
          Buffer.from("Uvicorn running on http://127.0.0.1:54321\n"),
        );
      }, 0);
      await promise;

      const spawnOpts = spawnMock.mock.calls[0][2] as { env: Record<string, string> };
      expect(spawnOpts.env.MY_COWORK_EXAMPLE_SKILLS).toBe(exampleSkills);
    } finally {
      (process as { resourcesPath?: string }).resourcesPath = prev;
      fs.rmSync(resources, { recursive: true, force: true });
    }
  });
});

describe("python_runner startup lifecycle", () => {
  let proc: MockChildProcess;
  const requests: Array<EventEmitter & { destroy: ReturnType<typeof vi.fn>; setTimeout: ReturnType<typeof vi.fn> }> = [];
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    proc = new MockChildProcess();
    requests.length = 0;
    spawnMock.mockReturnValue(proc);
    // Do not send actual signals when tests run on POSIX.
    vi.spyOn(process, "kill").mockReturnValue(true);
    getMock.mockImplementation(() => {
      const req = Object.assign(new EventEmitter(), { destroy: vi.fn(), setTimeout: vi.fn() });
      requests.push(req);
      return req;
    });
  });
  afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

  it("allows a cold start slower than 15 seconds", async () => {
    const pending = start({ cwd: "/fake", dev: true });
    proc.stderr.emit("data", Buffer.from("Uvicorn running on http://127.0.0.1:54321\n"));
    await vi.advanceTimersByTimeAsync(20_000);
    getMock.mock.calls[0][1]({ statusCode: 200, resume: vi.fn() });
    expect((await pending).port).toBe(54321);
    expect(proc.kill).not.toHaveBeenCalled();
    expect(spawnSyncMock).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("times out and stops its process tree even when no port is printed", async () => {
    const pending = start({ cwd: "/fake", dev: true, healthTimeoutMs: 100 }).catch(e => e);
    await vi.advanceTimersByTimeAsync(101);
    expect(await pending).toBeInstanceOf(Error);
    expect(process.platform === "win32" ? spawnSyncMock : process.kill).toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("bounds hanging health requests and cleans them up", async () => {
    const pending = start({ cwd: "/fake", dev: true, healthTimeoutMs: 100 }).catch(e => e);
    proc.stderr.emit("data", Buffer.from("Listening on 127.0.0.1:54321\n"));
    await vi.advanceTimersByTimeAsync(101);
    expect(await pending).toBeInstanceOf(Error);
    expect(requests[0].destroy).toHaveBeenCalled();
    expect(process.platform === "win32" ? spawnSyncMock : process.kill).toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("rejects immediately if the process exits after announcing its port", async () => {
    const pending = start({ cwd: "/fake", dev: true }).catch(e => e);
    proc.stderr.emit("data", Buffer.from("Listening on 127.0.0.1:54321\n"));
    proc.emit("exit", 1);
    expect((await pending).message).toMatch(/exited.*1/);
    expect(requests[0].destroy).toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("waits for the complete port line when output is split", async () => {
    const pending = start({ cwd: "/fake", dev: true });
    proc.stderr.emit("data", Buffer.from("Listening on 127.0.0.1:54"));
    expect(getMock).not.toHaveBeenCalled();
    proc.stderr.emit("data", Buffer.from("321\n"));
    getMock.mock.calls[0][1]({ statusCode: 200, resume: vi.fn() });
    expect((await pending).port).toBe(54321);
  });

  it("cancels during startup and ignores late success before retrying", async () => {
    const controller = new AbortController();
    const pending = start({ cwd: "/fake", dev: true, signal: controller.signal }).catch(e => e);
    proc.stderr.emit("data", Buffer.from("Listening on 127.0.0.1:54321\n"));
    const late = getMock.mock.calls[0][1];
    controller.abort();
    expect((await pending).name).toBe("AbortError");
    late({ statusCode: 200, resume: vi.fn() });
    const next = new MockChildProcess();
    spawnMock.mockReturnValue(next);
    const retry = start({ cwd: "/fake", dev: true });
    next.stderr.emit("data", Buffer.from("Listening on 127.0.0.1:54322\n"));
    getMock.mock.calls[1][1]({ statusCode: 200, resume: vi.fn() });
    expect((await retry).url).toBe("http://127.0.0.1:54322");
    expect(vi.getTimerCount()).toBe(0);
  });
});
