import { ExternalLink } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import SearchInput from "@/components/hub/SearchInput";
import SkillHubCard, { type HubSkill } from "@/components/skills/SkillHubCard";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export const HUB_CATEGORIES: { id: string; label: string }[] = [
  { id: "", label: "全部" },
  { id: "office-efficiency", label: "办公效率" },
  { id: "content-creation", label: "内容创作" },
  { id: "dev-programming", label: "开发编程" },
  { id: "data-analysis", label: "数据分析" },
  { id: "design-media", label: "设计多媒体" },
  { id: "ai-agent", label: "AI Agent" },
  { id: "knowledge-management", label: "知识管理" },
  { id: "professional", label: "行业专业" },
];

const PAGE_SIZE = 12;
const DEBOUNCE_MS = 300;

interface SkillHubSuiteProps {
  installedIds: Set<string>;
  onInstalled: () => void;
}

export default function SkillHubSuite({
  installedIds,
  onInstalled,
}: SkillHubSuiteProps) {
  const [category, setCategory] = useState("");
  const [query, setQuery] = useState("");
  const [debouncedKeyword, setDebouncedKeyword] = useState("");
  const [skills, setSkills] = useState<HubSkill[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(false);
  const [installingSlug, setInstallingSlug] = useState<string | null>(null);
  const [installedSlugs, setInstalledSlugs] = useState<Set<string>>(new Set());

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedKeyword(query.trim()), DEBOUNCE_MS);
    return () => window.clearTimeout(t);
  }, [query]);

  function searchNow() {
    setDebouncedKeyword(query.trim());
  }

  const loadPage = useCallback(
    async (nextPage: number, replace: boolean) => {
      const backendUrl = await window.api.getBackendUrl();
      if (!backendUrl) {
        setStatus("后端未连接");
        return;
      }
      const params = new URLSearchParams();
      params.set("page", String(nextPage));
      params.set("pageSize", String(PAGE_SIZE));
      params.set("sortBy", "score");
      if (debouncedKeyword.trim()) params.set("keyword", debouncedKeyword.trim());
      if (category) params.set("category", category);
      setLoading(true);
      try {
        const res = await fetch(`${backendUrl}/api/skillhub?${params.toString()}`);
        if (!res.ok) {
          setStatus(`加载失败 ${res.status}`);
          return;
        }
        const data = (await res.json()) as { skills?: HubSkill[]; total?: number };
        const list = data.skills || [];
        setSkills((prev) => (replace ? list : [...prev, ...list]));
        setTotal(data.total ?? list.length);
        setPage(nextPage);
        setStatus("");
      } catch (e) {
        setStatus(e instanceof Error ? e.message : "加载失败");
      } finally {
        setLoading(false);
      }
    },
    [category, debouncedKeyword],
  );

  useEffect(() => {
    void loadPage(1, true);
  }, [loadPage]);

  async function install(skill: HubSkill) {
    const backendUrl = await window.api.getBackendUrl();
    if (!backendUrl) return;
    setInstallingSlug(skill.slug);
    try {
      const res = await fetch(`${backendUrl}/api/skillhub/install`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ handle: skill.handle, slug: skill.slug }),
      });
      if (!res.ok) {
        setStatus(`安装失败 ${res.status}`);
        return;
      }
      setInstalledSlugs((prev) => new Set(prev).add(skill.slug));
      setStatus(`已安装「${skill.name}」`);
      onInstalled();
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "安装失败");
    } finally {
      setInstallingSlug(null);
    }
  }

  function isInstalled(skill: HubSkill): boolean {
    return (
      installedIds.has(skill.slug) ||
      installedIds.has(skill.name) ||
      installedSlugs.has(skill.slug)
    );
  }

  return (
    <section className="mt-8">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-ds-text-neutral-default-default">
          推荐 SkillHub 套件
        </h3>
        <div className="flex items-center gap-3 text-xs text-ds-text-neutral-muted-default">
          {debouncedKeyword.trim() ? <span>共 {total} 个结果</span> : null}
          <span>综合评分</span>
          <a
            href="https://skillhub.cn/"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 hover:text-ds-text-neutral-default-default"
          >
            skillhub.cn
            <ExternalLink className="h-3 w-3" />
          </a>
        </div>
      </div>
      <div className="mb-3 max-w-md">
        <SearchInput
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onSearch={searchNow}
          placeholder="搜索 SkillHub 技能…"
        />
      </div>
      <div className="mb-4 flex flex-wrap gap-1.5">
        {HUB_CATEGORIES.map((c) => (
          <button
            key={c.id || "all"}
            type="button"
            className={cn(
              "rounded-lg px-2.5 py-1 text-xs transition-colors",
              category === c.id
                ? "bg-ds-bg-neutral-strong-default font-medium text-ds-text-neutral-default-default"
                : "bg-ds-bg-neutral-subtle-default text-ds-text-neutral-muted-default hover:bg-ds-bg-neutral-strong-default",
            )}
            onClick={() => setCategory(c.id)}
          >
            {c.label}
          </button>
        ))}
      </div>
      {status && (
        <p className="mb-3 text-xs text-ds-text-neutral-subtle-default">{status}</p>
      )}
      {skills.length === 0 && !loading ? (
        <p className="py-6 text-center text-sm text-ds-text-neutral-muted-default">
          未找到技能
        </p>
      ) : (
        <div className="grid w-full grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {skills.map((skill) => (
            <SkillHubCard
              key={`${skill.handle}/${skill.slug}`}
              skill={skill}
              installed={isInstalled(skill)}
              installing={installingSlug === skill.slug}
              onInstall={() => void install(skill)}
            />
          ))}
        </div>
      )}
      {skills.length < total && (
        <div className="mt-4 flex justify-center">
          <Button
            variant="outline"
            size="sm"
            disabled={loading}
            onClick={() => void loadPage(page + 1, false)}
          >
            {loading ? "加载中…" : "加载更多"}
          </Button>
        </div>
      )}
      <p className="mt-4 text-xs text-ds-text-neutral-muted-default">
        公开技能来自{" "}
        <a
          href="https://skillhub.cn/"
          target="_blank"
          rel="noreferrer"
          className="underline"
        >
          skillhub.cn
        </a>
        ，安装后写入本地 skills/，请自行确认来源。
      </p>
    </section>
  );
}
