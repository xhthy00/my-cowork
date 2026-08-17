/**
 * Memory list UI — shell aligned with Eigent Agents pages;
 * Eigent Memory.tsx is Coming Soon; we keep local CRUD.
 */
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";

interface MemoryRow {
  id: number;
  kind: string;
  content: string;
  created_at: number;
}

const MEMORY_KEY = "my-cowork-memory-on";

export function isMemoryEnabled(): boolean {
  const v = localStorage.getItem(MEMORY_KEY);
  return v !== "0";
}

export function setMemoryEnabled(on: boolean): void {
  localStorage.setItem(MEMORY_KEY, on ? "1" : "0");
}

export default function MemoryView() {
  const [rows, setRows] = useState<MemoryRow[]>([]);
  const [q, setQ] = useState("");
  const [draft, setDraft] = useState("");
  const [enabled, setEnabled] = useState(isMemoryEnabled);
  const [status, setStatus] = useState("");

  const load = useCallback(async () => {
    const backendUrl = await window.api.getBackendUrl();
    if (!backendUrl) {
      setStatus("后端未连接");
      return;
    }
    const url = q
      ? `${backendUrl}/api/memory?q=${encodeURIComponent(q)}&k=20`
      : `${backendUrl}/api/memory/list?limit=50`;
    const res = await fetch(url);
    if (!res.ok) {
      setStatus(`加载失败 ${res.status}`);
      return;
    }
    const data = (await res.json()) as { items: MemoryRow[] };
    setRows(data.items || []);
    setStatus("");
  }, [q]);

  useEffect(() => {
    void load();
  }, [load]);

  function toggleEnabled(next: boolean) {
    setEnabled(next);
    localStorage.setItem(MEMORY_KEY, next ? "1" : "0");
  }

  async function addMemory() {
    const text = draft.trim();
    if (!text) return;
    const backendUrl = await window.api.getBackendUrl();
    if (!backendUrl) return;
    await fetch(`${backendUrl}/api/memory`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: text, kind: "note" }),
    });
    setDraft("");
    await load();
  }

  async function remove(id: number) {
    const backendUrl = await window.api.getBackendUrl();
    if (!backendUrl) return;
    await fetch(`${backendUrl}/api/memory/${id}`, { method: "DELETE" });
    await load();
  }

  return (
    <div className="m-auto flex h-auto w-full flex-1 flex-col">
      <div className="flex w-full items-center justify-between px-6 pb-6 pt-8">
        <div className="text-heading-sm font-bold text-ds-text-neutral-default-default">
          记忆
        </div>
        <div className="flex items-center gap-2 text-xs text-ds-text-neutral-muted-default">
          <span>注入长期记忆</span>
          <Switch checked={enabled} onCheckedChange={toggleEnabled} />
        </div>
      </div>

      <div className="mb-12 flex flex-col gap-4 rounded-2xl bg-ds-bg-neutral-default-default px-6 py-4">
        <textarea
          rows={2}
          placeholder="手动添加一条记忆…"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          className="w-full resize-none rounded-xl border border-ds-border-neutral-default-default bg-ds-bg-neutral-subtle-default p-3 text-sm outline-none"
        />
        <div className="flex flex-wrap items-center gap-2">
          <input
            className="h-8 min-w-[160px] flex-1 rounded-lg border border-ds-border-neutral-default-default bg-ds-bg-neutral-subtle-default px-3 text-xs outline-none"
            placeholder="搜索…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <Button size="sm" onClick={() => void addMemory()}>
            添加
          </Button>
        </div>
        {status && <p className="text-xs text-ds-text-neutral-subtle-default">{status}</p>}
        <ul className="flex flex-col gap-2">
          {rows.map((r) => (
            <li
              key={r.id}
              className="flex items-start justify-between gap-3 rounded-2xl bg-ds-bg-neutral-subtle-default p-4"
            >
              <div className="min-w-0">
                <span className="rounded-md bg-ds-bg-neutral-default-default px-1.5 py-0.5 text-[11px] text-ds-text-neutral-subtle-default">
                  {r.kind}
                </span>
                <p className="mt-2 text-sm text-ds-text-neutral-default-default">{r.content}</p>
              </div>
              <Button size="sm" variant="ghost" onClick={() => void remove(r.id)}>
                删除
              </Button>
            </li>
          ))}
          {!rows.length && (
            <p className="py-8 text-center text-sm text-ds-text-neutral-muted-default">
              暂无记忆
            </p>
          )}
        </ul>
      </div>
    </div>
  );
}
