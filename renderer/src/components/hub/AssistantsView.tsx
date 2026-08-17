/**
 * Builtin office assistants list — scene catalog with categories + prompt chips.
 */
import { useEffect, useMemo, useState } from "react";
import { Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
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

export default function AssistantsView() {
  const [items, setItems] = useState<AssistantItem[]>([]);
  const [error, setError] = useState("");
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
      }
    })();
  }, []);

  const grouped = useMemo(() => {
    const buckets = new Map<string, AssistantItem[]>();
    for (const a of items) {
      const cat = CATEGORY_ORDER.includes(
        a.category as (typeof CATEGORY_ORDER)[number],
      )
        ? (a.category as (typeof CATEGORY_ORDER)[number])
        : "general";
      const list = buckets.get(cat) ?? [];
      list.push(a);
      buckets.set(cat, list);
    }
    return CATEGORY_ORDER.filter((c) => (buckets.get(c)?.length ?? 0) > 0).map(
      (c) => ({
        category: c,
        label: CATEGORY_LABEL[c],
        items: buckets.get(c) ?? [],
      }),
    );
  }, [items]);

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
    <div className="m-auto flex h-auto w-full flex-1 flex-col">
      <div className="flex w-full items-center justify-between px-6 pb-6 pt-8">
        <div>
          <div className="text-heading-sm font-bold">办公助手</div>
          <p className="mt-1 text-sm text-ds-text-neutral-muted-default">
            按场景选择助手将预加载对应技能与规则；可点推荐提问直接开聊。生成后可自动高保真预览。
          </p>
        </div>
      </div>
      {error && (
        <div className="px-6 pb-4 text-sm text-red-600">{error}</div>
      )}
      <div className="mb-12 flex w-full flex-col gap-10 px-6">
        {grouped.map((group) => (
          <section key={group.category}>
            <h3 className="mb-3 text-sm font-semibold text-ds-text-neutral-muted-default">
              {group.label}
            </h3>
            <div className="grid w-full grid-cols-1 gap-4 md:grid-cols-2">
              {group.items.map((a) => (
                <div
                  key={a.id}
                  className="flex flex-col rounded-2xl bg-ds-bg-neutral-default-default p-5"
                >
                  <div className="mb-2 flex items-center gap-2">
                    <Sparkles className="h-4 w-4 text-ds-icon-neutral-muted-default" />
                    <div className="font-semibold text-ds-text-neutral-default-default">
                      {a.name}
                    </div>
                  </div>
                  <p className="mb-3 flex-1 text-sm text-ds-text-neutral-muted-default">
                    {a.description}
                  </p>
                  <div className="mb-3 flex flex-wrap gap-1">
                    {a.enabled_skills.map((s) => (
                      <span
                        key={s}
                        className="rounded-md bg-ds-bg-neutral-subtle-default px-2 py-0.5 text-xs text-ds-text-neutral-muted-default"
                      >
                        {s}
                      </span>
                    ))}
                  </div>
                  {a.prompts?.length > 0 && (
                    <div className="mb-4 flex flex-col gap-1.5">
                      {a.prompts.slice(0, 3).map((p) => (
                        <button
                          key={p}
                          type="button"
                          className="rounded-lg bg-ds-bg-neutral-subtle-default px-2.5 py-1.5 text-left text-xs text-ds-text-neutral-default-default transition-opacity hover:opacity-80"
                          onClick={() => startWith(a, p)}
                        >
                          {p}
                        </button>
                      ))}
                    </div>
                  )}
                  <Button size="sm" onClick={() => startWith(a)}>
                    用此助手开始
                  </Button>
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
