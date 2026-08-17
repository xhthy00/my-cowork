/**
 * Adapted from eigent: pages/Agents/Skills.tsx
 * Data: GET/PATCH/DELETE/import via /api/skills (not Eigent skillsStore).
 */
import { Plus } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import SearchInput from "@/components/hub/SearchInput";
import SkillHubSuite from "@/components/skills/SkillHubSuite";
import SkillListItem, {
  type SkillItem,
  type SkillScope,
} from "@/components/skills/SkillListItem";
import AlertDialog from "@/components/ui/alertDialog";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

function isExampleSkill(skill: SkillItem): boolean {
  return Boolean(skill.isExample);
}

export default function SkillsView() {
  const [skills, setSkills] = useState<SkillItem[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [status, setStatus] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<SkillItem | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    const backendUrl = await window.api.getBackendUrl();
    if (!backendUrl) {
      setStatus("后端未连接");
      return;
    }
    const res = await fetch(`${backendUrl}/api/skills`);
    if (!res.ok) {
      setStatus(`加载失败 ${res.status}`);
      return;
    }
    const data = (await res.json()) as { skills: SkillItem[] };
    setSkills(data.skills || []);
    setStatus("");
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function patch(id: string, body: Record<string, unknown>) {
    const backendUrl = await window.api.getBackendUrl();
    if (!backendUrl) return;
    await fetch(`${backendUrl}/api/skills/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    await load();
  }

  async function remove(id: string) {
    const backendUrl = await window.api.getBackendUrl();
    if (!backendUrl) return;
    await fetch(`${backendUrl}/api/skills/${id}`, { method: "DELETE" });
    await load();
  }

  async function importZip(file: File) {
    const backendUrl = await window.api.getBackendUrl();
    if (!backendUrl) return;
    const buf = await file.arrayBuffer();
    const bytes = new Uint8Array(buf);
    let binary = "";
    for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]!);
    const zip_base64 = btoa(binary);
    const res = await fetch(`${backendUrl}/api/skills/import`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ zip_base64, filename: file.name }),
    });
    setStatus(res.ok ? "已导入技能" : `导入失败 ${res.status}`);
    await load();
  }

  const yourSkills = useMemo(() => {
    const q = searchQuery.toLowerCase();
    return skills
      .filter((s) => !isExampleSkill(s))
      .filter(
        (s) =>
          !q ||
          s.name.toLowerCase().includes(q) ||
          s.description.toLowerCase().includes(q) ||
          s.id.toLowerCase().includes(q),
      );
  }, [skills, searchQuery]);

  const exampleSkills = useMemo(() => {
    const q = searchQuery.toLowerCase();
    return skills
      .filter((s) => isExampleSkill(s))
      .filter(
        (s) =>
          !q ||
          s.name.toLowerCase().includes(q) ||
          s.description.toLowerCase().includes(q) ||
          s.id.toLowerCase().includes(q),
      );
  }, [skills, searchQuery]);

  function renderList(list: SkillItem[], emptyMsg: string, allowAdd: boolean) {
    if (!list.length) {
      return (
        <SkillListItem
          variant="placeholder"
          message={searchQuery ? "未找到技能" : emptyMsg}
          addButtonText={allowAdd && !searchQuery ? "添加第一个技能" : undefined}
          onAddClick={
            allowAdd && !searchQuery ? () => fileRef.current?.click() : undefined
          }
        />
      );
    }
    return (
      <div className="flex flex-col gap-3">
        {list.map((skill) => (
          <SkillListItem
            key={skill.id}
            skill={skill}
            onToggle={(enabled) => void patch(skill.id, { enabled })}
            onScopeChange={(scope: SkillScope) => void patch(skill.id, { scope })}
            onDelete={
              isExampleSkill(skill) ? undefined : () => setDeleteTarget(skill)
            }
          />
        ))}
      </div>
    );
  }

  return (
    <div className="m-auto flex h-auto w-full flex-1 flex-col">
      <div className="flex w-full items-center justify-between px-6 pb-6 pt-8">
        <div className="text-heading-sm font-bold text-ds-text-neutral-default-default">
          技能
        </div>
      </div>

      <div className="mb-12 flex flex-col gap-6">
        <div className="flex w-full flex-col gap-4 rounded-2xl bg-ds-bg-neutral-default-default px-6 py-4">
          <Tabs defaultValue="your-skills" className="w-full">
            <div className="z-10 flex w-full items-center justify-between gap-4 border-x-0 border-b-[0.5px] border-t-0 border-solid border-ds-border-neutral-default-default bg-ds-bg-neutral-default-default">
              <TabsList appearance="border" className="h-auto flex-1 justify-start">
                <TabsTrigger value="your-skills">您的技能</TabsTrigger>
                <TabsTrigger value="example-skills">内置技能</TabsTrigger>
              </TabsList>
              <div className="mb-2 flex items-center gap-2">
                <SearchInput
                  variant="icon"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="搜索技能…"
                />
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => fileRef.current?.click()}
                >
                  <Plus className="h-4 w-4" />
                  添加技能
                </Button>
                <input
                  ref={fileRef}
                  type="file"
                  accept=".zip,application/zip"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    e.target.value = "";
                    if (f) void importZip(f);
                  }}
                />
              </div>
            </div>
            {status && (
              <p className="mt-2 text-xs text-ds-text-neutral-subtle-default">{status}</p>
            )}
            <TabsContent value="your-skills" className="mt-4">
              {renderList(yourSkills, "还没有自定义技能", true)}
            </TabsContent>
            <TabsContent value="example-skills" className="mt-4">
              {renderList(exampleSkills, "暂无内置技能", false)}
            </TabsContent>
          </Tabs>
          <SkillHubSuite
            installedIds={new Set(skills.map((s) => s.id))}
            onInstalled={() => void load()}
          />
        </div>
      </div>

      <AlertDialog
        open={!!deleteTarget}
        title="删除技能"
        description={
          deleteTarget
            ? `确定删除「${deleteTarget.name}」？此操作不可撤销。`
            : undefined
        }
        confirmLabel="删除"
        confirmVariant="destructive"
        onConfirm={() => {
          if (deleteTarget) void remove(deleteTarget.id);
          setDeleteTarget(null);
        }}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
