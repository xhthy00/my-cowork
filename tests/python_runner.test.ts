import { EventEmitter } from "events";
import { beforeEach, describe, expect, it, vi } from "vitest";

// ── hoisted mocks ──────────────────────────────────────────────────────────
const { spawnMock, getMock } = vi.hoisted(() => ({
  spawnMock: vi.fn(),
  getMock: vi.fn(),
}));

vi.mock("child_process", () => ({ spawn: spawnMock }));
vi.mock("http", () => ({ get: getMock }));

// ── helpers ───────────────────────────────────────────────────────────────
class MockChildProcess extends EventEmitter {
  stdin = { write: vi.fn() };
  stdout = new EventEmitter();
  stderr = new EventEmitter();
}

function fakeHealthOk(): any {
  const res = new EventEmitter() as any;
  res.statusCode = 200;
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
      return new EventEmitter();
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
      ["run", "uvicorn", "app.main:app", "--port", "0"],
      { cwd: "/fake/cwd", env: { ...process.env } },
    );
  });

  it("passes env overrides through to spawn", async () => {
    spawnMock.mockReturnValue(new MockChildProcess());

    getMock.mockImplementation((_url: string, cb: any) => {
      const res = fakeHealthOk();
      setTimeout(() => cb(res), 0);
      return new EventEmitter();
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
});
