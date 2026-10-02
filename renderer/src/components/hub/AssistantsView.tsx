import { apiFetch as fetch } from "@/api/backend";
/**
 * Builtin office assistants catalog with categories and recommended prompts.
 */
import { useEffect, useMemo, useState } from "react";
import { Sparkles, FileText, Presentation, ChartPie, Scale, ArrowUpRight, Search, LayoutGrid } from "lucide-react";

import { usePageTabStore } from "@/store/pageTab";
import { useSessionsStore } from "@/store/sessions";

export interface AssistantItem {
  id: string;
  name: string;
  description: string;
  category?: string;
  enabled_skills: string[];
  prompts: string[];
  rules?: string;
  source: string;
}

const CATEGORY_ORDER = [
  "presentation",
  "document",
  "spreadsheet",
  "legal",
  "general",
] as const;

const CATEGORY_LABEL: Record<(typeof CATEGORY_ORDER)[number], string> = {
  presentation: "演示文稿",
  document: "文档",
  spreadsheet: "表格",
  legal: "法务",
  general: "通用",
};

const SKILL_LABELS: Record<string, string> = {
  officecli: "办公文档", "officecli-pptx": "演示制作", "officecli-docx": "Word 文档",
  "officecli-xlsx": "数据表格", "officecli-pitch-deck": "融资路演", "officecli-word-form": "表单制作",
  "official-document-writing": "公文写作", "officecli-data-dashboard": "数据看板",
  "officecli-financial-model": "财务建模", "china-legal-counsel": "合同与合规",
};

export default function AssistantsView() {
  const [items, setItems] = useState<AssistantItem[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const createSession = useSessionsStore((s) => s.createSession);
  const setWorkspaceView = usePageTabStore((s) => s.setWorkspaceView);

  useEffect(() => {
    void (async () => {
      try {
        const backendUrl = await window.api.getBackendUrl();
        if (!backendUrl) {
          setError("后端未连接");
          return;
        }
        const data = await fetch(`${backendUrl}/api/assistants`).then((r) =>
          r.json(),
        );
        setItems(Array.isArray(data.assistants) ? data.assistants : []);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally { setLoading(false); }
    })();
  }, []);

  const categoryIcon = { presentation: Presentation, document: FileText, spreadsheet: ChartPie, legal: Scale, general: LayoutGrid };
  const filtered = useMemo(() => items.filter(a => (category === "all" || (a.category || "general") === category) && `${a.name} ${a.description}`.toLowerCase().includes(query.trim().toLowerCase())), [items, category, query]);

  function startWith(a: AssistantItem, prompt?: string) {
    const fill = (prompt?.trim() || a.prompts?.[0] || "").trim();
    createSession(a.name, {
      assistantId: a.id,
      assistantName: a.name,
      enabledSkillIds: a.enabled_skills,
      assistantPrompts: a.prompts,
    });
    setWorkspaceView("workspace");
    // ChatBar mounts after workspace switch — delay fill so the listener exists.
    if (fill) {
      window.setTimeout(() => {
        window.dispatchEvent(
          new CustomEvent("my-cowork:composer-fill", { detail: fill }),
        );
      }, 80);
    }
  }

  return (
    <div className="assistants-view w-full">
      <div className="assistant-toolbar">
        <label className="assistant-search"><Search size={18} aria-hidden /><input aria-label="搜索助理" placeholder="搜索助理名称或描述" value={query} onChange={e => setQuery(e.target.value)} /></label>
      </div>
      {error && <div role="alert" className="mb-4 text-sm text-ds-text-error-default-default">{error}</div>}
      {loading && <p role="status" className="py-8 text-sm text-ds-text-neutral-muted-default">正在加载助理…</p>}
      <section aria-labelledby="assistant-catalog-title" className="assistant-catalog">
        <div className="assistant-catalog-heading"><h2 id="assistant-catalog-title" className="sr-only">办公助理</h2><span>{filtered.length} 位助理</span></div>
        <div className="assistant-filters" role="group" aria-label="助理分类">{[["all", "全部"], ...CATEGORY_ORDER.map(c => [c, CATEGORY_LABEL[c]])].map(([id, label]) => <button type="button" key={id} aria-pressed={category === id} onClick={() => setCategory(id)}>{label}</button>)}</div>
        <div className="assistant-grid">{filtered.map(a => { const Icon = categoryIcon[a.category as keyof typeof categoryIcon] || Sparkles; return <article key={a.id} className="assistant-card" data-category={a.category || "general"}>
          <div className="assistant-card-header"><span className="assistant-avatar"><Icon size={24} aria-hidden /></span><div><h3>{a.name}</h3><span>{CATEGORY_LABEL[a.category as keyof typeof CATEGORY_LABEL] || "通用"}助理</span></div><button type="button" aria-label={`使用${a.name}`} title="开始任务" className="assistant-start" onClick={() => startWith(a)}><ArrowUpRight size={18} aria-hidden /></button></div>
          <p>{a.description}</p>
          <div className="assistant-tags">{a.enabled_skills.map(skill => <span key={skill} title={skill}>{SKILL_LABELS[skill] || skill}</span>)}</div>
          {a.prompts?.length > 0 && <div className="assistant-prompts">{a.prompts.slice(0, 2).map(p => <button key={p} type="button" className="assistant-prompt" onClick={() => startWith(a, p)}>{p}<ArrowUpRight size={13} aria-hidden /></button>)}</div>}
        </article>; })}</div>
        {!loading && !error && filtered.length === 0 && <p className="assistant-empty">{items.length ? "没有找到匹配的助理，试试其他关键词或分类。" : "暂无可用助理"}</p>}
      </section>
    </div>
  );
}
