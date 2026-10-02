import { ChildProcess } from "child_process";
import { createInterface } from "readline";

export interface RuntimeState {
  generation: string;
  active: number;
  tasks: string[];
  apps: Array<{ id: string; version?: string; dev_revision?: string; enabled?: boolean; status: string; error?: string }>;
}
export interface LifecycleStatus {
  busy: boolean;
  phase: string;
  appId?: string;
  message?: string;
  detail?: string;
  active?: number;
  tasks?: string[];
  generation?: string;
}
export interface MaintenancePipe {
  call<T = any>(request: Record<string, unknown>): Promise<T>;
  close(): void;
}

export class JsonPipe implements MaintenancePipe {
  private pending?: { resolve: (value: any) => void; reject: (error: Error) => void; timer: NodeJS.Timeout };
  private error?: Error;
  constructor(private proc: ChildProcess) {
    let stderr = "";
    proc.stderr?.on("data", (data) => { stderr = (stderr + String(data)).slice(-3000); });
    const fail = (error: Error) => {
      this.error = error;
      if (this.pending) {
        clearTimeout(this.pending.timer);
        this.pending.reject(error);
        this.pending = undefined;
      }
    };
    proc.on("error", fail);
    proc.on("exit", (code) => fail(new Error(`维护进程已退出 (${code}) ${stderr}`)));
    const lines = createInterface({ input: proc.stdout! });
    lines.on("line", (line) => {
      const pending = this.pending;
      if (!pending) return;
      try {
        const response = JSON.parse(line);
        clearTimeout(pending.timer);
        this.pending = undefined;
        if (response.ok) pending.resolve(response.result);
        else pending.reject(new Error(response.error));
      } catch { fail(new Error("维护进程返回了无效响应")); }
    });
  }
  call<T>(request: Record<string, unknown>): Promise<T> {
    if (this.error) return Promise.reject(this.error);
    if (this.pending) return Promise.reject(new Error("维护命令必须串行执行"));
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.error = new Error("维护命令超时，请重试恢复");
        this.pending = undefined;
        this.close();
        reject(this.error);
      }, 120_000);
      this.pending = { resolve, reject, timer };
      this.proc.stdin!.write(JSON.stringify(request) + "\n");
    });
  }
  close(): void { this.proc.stdin?.end(); }
}

interface Hooks {
  pipe(): MaintenancePipe;
  running(): boolean;
  modelReady(): Promise<boolean>;
  start(token?: string): Promise<void>;
  stop(): Promise<void>;
  runtime(action?: "drain" | "open"): Promise<RuntimeState>;
  publish(runtime: RuntimeState | null): void;
  changed(status: LifecycleStatus): void;
}

export class IndustryLifecycle {
  status: LifecycleStatus = { busy: false, phase: "idle" };
  private cancelRequested = false;
  private inFlight?: Promise<unknown>;
  private requestKey?: string;
  constructor(private hooks: Hooks) {}

  private update(phase: string, extra: Partial<LifecycleStatus> = {}) {
    this.status = { ...this.status, phase, ...extra };
    this.hooks.changed(this.status);
  }

  async query(request: Record<string, unknown>): Promise<any> {
    const pipe = this.hooks.pipe();
    try { return await pipe.call(request); } finally { pipe.close(); }
  }

  cancel(): void {
    if (this.status.busy && this.status.phase === "draining") this.cancelRequested = true;
  }

  run(request: Record<string, unknown>): Promise<unknown> {
    const key = JSON.stringify(request);
    if (this.inFlight) return this.requestKey === key ? this.inFlight : Promise.reject(new Error("已有应用操作正在进行，请等待完成"));
    this.requestKey = key;
    this.cancelRequested = false;
    this.update("staged", { busy: true, appId: request.app_id as string | undefined, message: undefined, detail: undefined, active: 0, tasks: [] });
    const promise = this.execute(request).finally(() => {
      this.inFlight = undefined;
      this.requestKey = undefined;
      this.update(this.status.phase, { busy: false, active: 0, tasks: [] });
    });
    this.inFlight = promise;
    return promise;
  }

  private async drain(pipe: MaintenancePipe): Promise<boolean> {
    this.update("draining");
    await pipe.call({ command: "draining" });
    if (this.hooks.running()) {
      let state = await this.hooks.runtime("drain");
      while (state.active > 0 && !this.cancelRequested) {
        this.update("draining", { active: state.active, tasks: state.tasks });
        await new Promise((resolve) => setTimeout(resolve, 300));
        state = await this.hooks.runtime();
      }
    }
    if (!this.cancelRequested) return true;
    await pipe.call({ command: "cancel" });
    if (this.hooks.running()) await this.hooks.runtime("open");
    this.update("cancelled", { message: "已取消更新，原有工作可继续", active: 0, tasks: [] });
    return false;
  }

  private async activate(pipe: MaintenancePipe, candidate: { token: string } | null, ordinaryRestart = false): Promise<RuntimeState> {
    this.update(candidate ? "starting" : "restarting");
    await this.hooks.start(candidate?.token);
    let runtime = await this.hooks.runtime();
    let failed = runtime.apps.filter((app) => app.status !== "ready");
    if (ordinaryRestart && failed.length) {
      await this.hooks.stop();
      const safe: { token: string } = await pipe.call({ command: "disable_failed", failures: failed });
      await this.hooks.start(safe.token);
      runtime = await this.hooks.runtime();
      this.update("starting", { message: "启动失败的应用已停用，业务数据已保留，可在管理菜单中处理。" });
      failed = runtime.apps.filter((app) => app.status !== "ready");
    }
    if (failed.length) throw new Error(failed.map((app) => `${app.id}: ${app.error || app.status}`).join("\n"));
    if (candidate) await pipe.call({ command: "commit" });
    // Commit is the conservative boundary: failure after this point must never
    // silently overwrite data from the newly committed version.
    await this.hooks.runtime("open");
    this.hooks.publish(runtime);
    return runtime;
  }

  private async execute(request: Record<string, unknown>) {
    const pipe = this.hooks.pipe();
    let stopped = false;
    let begun = false;
    let recovering = false;
    try {
      if (request.action === "retry" && request.app_id) await pipe.call({ command: "retry", app_id: request.app_id });
      let existing: any = await pipe.call({ command: "list" });
      if (request.action === "disable" && existing.operation && !["committed", "restored", "cancelled"].includes(existing.operation.phase)) {
        recovering = true;
        await this.hooks.stop();
        this.hooks.publish(null);
        await pipe.call({ command: "quarantine" });
        existing = await pipe.call({ command: "list" });
        request = { action: "restart" };
      }
      const unfinished = existing.operation && !["committed", "restored", "cancelled"].includes(existing.operation.phase);
      if (unfinished) {
        recovering = true;
        // A surviving process must release its OS lock before any restore. We
        // only stop our own child; an unknown owner makes maintenance fail.
        if (this.hooks.running()) await this.hooks.stop();
        this.hooks.publish(null);
        const candidate: any = await pipe.call({ command: "restore" });
        if (!await this.hooks.modelReady()) {
          this.update("recovery_required", { appId: existing.operation.app_id, message: "数据已保护，请配置模型后重试恢复并验证启动" });
          return;
        }
        const runtime = await this.activate(pipe, candidate);
        this.update("restored", { generation: runtime.generation, message: "已处理上次中断，原版本与数据已恢复" });
        if (request.action !== "restart" && request.action !== "retry") return;
        return;
      }
      if (request.action === "retry") request = { ...request, action: "restart" };
      // Saving a ZIP is useful without a model, but migrations must wait.
      const op: any = await pipe.call({ command: "begin", ...request });
      if (op.unchanged && this.hooks.running()) {
        this.update("committed", { message: "源码内容未变，继续使用当前修订。" });
        return op;
      }
      if (op.unchanged) {
        request = { action: "restart" };
        await pipe.call({ command: "begin", ...request });
      }
      begun = true;
      this.update("staged", { appId: op.app_id });
      if (!await this.hooks.modelReady()) {
        if (!await this.drain(pipe)) return;
        await this.hooks.stop();
        stopped = true;
        this.hooks.publish(null);
        if (["disable", "remove"].includes(String(request.action))) {
          await pipe.call({ command: "prepare" });
          await pipe.call({ command: "commit" });
          this.update("committed", { message: "操作已完成，业务数据已保留" });
          return;
        }
        await pipe.call({ command: "cancel", keep_candidate: true });
        this.update("pending_activation", { message: request.action === "restart" ? "配置模型后即可继续使用" : "应用已保存，配置模型后可在此启用" });
        return;
      }
      if (!await this.drain(pipe)) return;
      this.update("snapshot_ready", { active: 0, tasks: [] });
      await this.hooks.stop();
      stopped = true;
      this.hooks.publish(null);
      const candidate: any = await pipe.call({ command: "prepare" });
      const runtime = await this.activate(pipe, candidate, request.action === "restart");
      const messages: Record<string, string> = { develop: "开发修订已启用", install: "应用已启用，可继续使用", enable: "应用已启用", disable: "应用已停用", remove: "应用已移除，业务数据已保留", rollback: "已恢复到上次更新前，当前数据副本已保留" };
      this.update("committed", { generation: runtime.generation, message: messages[String(request.action)] || this.status.message });
      return { ...op, phase: "committed" };
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause);
      try {
        if (!begun && !recovering) {
          this.update("failed", { message: "操作未开始，请查看详情后重试。", detail: message });
        } else if (begun && !stopped) {
          await pipe.call({ command: "cancel" });
          if (this.hooks.running()) await this.hooks.runtime("open");
          this.update("failed", { message: "更新尚未开始，原有数据未改动。请查看详情后重试。", detail: message });
        } else {
          await this.hooks.stop();
          this.hooks.publish(null);
          const current: any = await pipe.call({ command: "list" });
          if (current.operation?.phase === "committed") throw new Error("版本已提交，但启动未完成；业务数据已保留，请重试启用。" + message);
          this.update("restoring", { detail: message });
          const candidate: any = await pipe.call({ command: "restore", error: message });
          const runtime = await this.activate(pipe, candidate);
          this.update("restored", { generation: runtime.generation, message: "更新未完成，已恢复原版本和数据。", detail: message });
        }
      } catch (recovery) {
        this.hooks.publish(null);
        await this.hooks.stop().catch(() => {});
        this.update("recovery_required", { message: "恢复尚未完成，数据和恢复点已保留。请重试恢复或停用此应用。", detail: `${message}\n${recovery instanceof Error ? recovery.message : recovery}` });
      }
      return { error: this.status.message, phase: this.status.phase };
    } finally {
      pipe.close();
    }
  }
}
