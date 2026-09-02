/**
 * Adapted from eigent: ChatBox/BottomBox/PickerPanel.tsx
 * Floating connector/skill list above the chat input; toggles @/# tokens.
 */
import { Check, Plus, Wrench } from "lucide-react";
import {
  Fragment,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { Button } from "@/components/ui/button";
import { getKnowledgeLogo } from "@/lib/knowledgeLogos";
import type { BoundKnowledgeBase } from "@/lib/knowledgeSources";
import {
  RICH_CONNECTOR_STYLE_CLASSES,
  RICH_SKILL_STYLE_CLASSES,
  connectorNameToToken,
  hashSkillLabel,
} from "@/lib/richText";
import { cn } from "@/lib/utils";
import { usePageTabStore } from "@/store/pageTab";
import type { SkillItem } from "@/components/skills/SkillListItem";

export interface PickerItem {
  id: string;
  name: string;
  token: string;
}

export interface PickerGroup {
  id: string;
  label?: string;
  items: PickerItem[];
}

export { connectorNameToToken };

export function skillNameToToken(name: string): string {
  const cleaned = name
    .replace(/[\\/*?:"<>|\s]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
  return `#${cleaned || "skill"}`;
}

function PickerPanelShell({
  title,
  groups,
  inputValue,
  onToggleItem,
  renderTag,
  renderLogo,
  loading = false,
  emptyLabel,
  emptyActionLabel,
  onEmptyAction,
  isSelected,
}: {
  title: string;
  groups: PickerGroup[];
  inputValue: string;
  onToggleItem: (item: PickerItem) => void;
  renderTag: (item: PickerItem) => ReactNode;
  renderLogo?: (item: PickerItem) => ReactNode;
  loading?: boolean;
  emptyLabel: string;
  emptyActionLabel: string;
  onEmptyAction: () => void;
  isSelected?: (item: PickerItem) => boolean;
}) {
  const nonEmptyGroups = groups.filter((g) => g.items.length > 0);
  const totalItems = nonEmptyGroups.reduce((n, g) => n + g.items.length, 0);

  return (
    <div className="flex w-full flex-col overflow-hidden rounded-2xl border border-solid border-ds-border-neutral-default-default bg-ds-bg-neutral-subtle-default">
      <div className="flex items-center gap-1 px-3 pb-1 pt-2">
        <span className="text-xs font-bold text-ds-text-neutral-muted-default">
          {title}
        </span>
        {totalItems > 0 && (
          <span className="text-xs font-bold text-ds-text-neutral-muted-default">
            {totalItems}
          </span>
        )}
      </div>
      <div className="flex max-h-[240px] flex-col gap-0.5 overflow-y-auto p-1">
        {loading ? (
          [0, 1, 2].map((i) => (
            <div
              key={i}
              className="h-8 w-full animate-pulse rounded-lg bg-ds-bg-neutral-strong-default"
            />
          ))
        ) : totalItems === 0 ? (
          <div className="flex w-full items-center justify-between gap-2 px-2 py-2">
            <span className="text-xs font-normal text-ds-text-neutral-muted-default">
              {emptyLabel}
            </span>
            <Button variant="ghost" size="xs" onClick={onEmptyAction}>
              {emptyActionLabel}
            </Button>
          </div>
        ) : (
          nonEmptyGroups.map((group) => (
            <Fragment key={group.id}>
              {group.label && (
                <div className="px-2 pb-0.5 pt-1.5 text-xs font-bold text-ds-text-neutral-muted-default">
                  {group.label}
                </div>
              )}
              {group.items.map((item) => {
                const added = isSelected
                  ? isSelected(item)
                  : inputValue.includes(item.token);
                return (
                  <button
                    key={item.id}
                    type="button"
                    aria-pressed={added}
                    className="group flex w-full items-center gap-2 rounded-xl border-0 bg-ds-bg-neutral-subtle-default px-2 py-1.5 text-left transition-colors hover:bg-ds-bg-neutral-default-default"
                    onClick={() => onToggleItem(item)}
                  >
                    {renderLogo?.(item) && (
                      <span className="flex h-5 w-5 shrink-0 items-center justify-center">
                        {renderLogo(item)}
                      </span>
                    )}
                    <span className="min-w-0 flex-1 overflow-hidden text-ellipsis whitespace-nowrap text-sm font-medium text-ds-text-neutral-default-default">
                      {item.name}
                    </span>
                    <span className="max-w-[45%] shrink-0 overflow-hidden whitespace-nowrap">
                      {renderTag(item)}
                    </span>
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center">
                      {added ? (
                        <Check
                          size={16}
                          className="text-ds-text-status-completed-default"
                        />
                      ) : (
                        <Plus
                          size={16}
                          className="text-ds-icon-neutral-muted-default opacity-0 transition-opacity group-hover:opacity-100"
                        />
                      )}
                    </span>
                  </button>
                );
              })}
            </Fragment>
          ))
        )}
      </div>
    </div>
  );
}

/** Local MCP servers from /api/mcp/servers (enabled only). */
export function ConnectorPickerPanel({
  inputValue,
  onToggleItem,
}: {
  inputValue: string;
  onToggleItem: (item: PickerItem) => void;
}) {
  const setHubTab = usePageTabStore((s) => s.setHubTab);
  const [items, setItems] = useState<PickerItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const url = await window.api.getBackendUrl();
        if (!url) return;
        const res = await fetch(`${url}/api/mcp/servers`);
        if (!res.ok) return;
        const data = (await res.json()) as {
          mcpServers?: Record<string, { enabled?: boolean; description?: string }>;
        };
        const next: PickerItem[] = Object.entries(data.mcpServers || {})
          .filter(([, cfg]) => cfg.enabled !== false)
          .map(([name]) => ({
            id: name,
            name,
            token: connectorNameToToken(name),
          }));
        if (!cancelled) setItems(next);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <PickerPanelShell
      title="连接器"
      groups={[{ id: "mcp", label: "MCP", items }]}
      inputValue={inputValue}
      onToggleItem={onToggleItem}
      renderTag={(item) => (
        <span
          className={cn(
            "rounded px-1 py-px text-xs font-medium",
            RICH_CONNECTOR_STYLE_CLASSES,
          )}
        >
          {item.token}
        </span>
      )}
      renderLogo={() => (
        <Wrench className="h-4 w-4 text-ds-icon-neutral-muted-default" aria-hidden />
      )}
      loading={loading}
      emptyLabel="暂无已启用的连接器"
      emptyActionLabel="管理连接器"
      onEmptyAction={() => setHubTab("connectors")}
    />
  );
}

/** Enabled skills from /api/skills. */
export function SkillPickerPanel({
  inputValue,
  onToggleItem,
}: {
  inputValue: string;
  onToggleItem: (item: PickerItem) => void;
}) {
  const setHubTab = usePageTabStore((s) => s.setHubTab);
  const [skills, setSkills] = useState<SkillItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const url = await window.api.getBackendUrl();
        if (!url) return;
        const res = await fetch(`${url}/api/skills`);
        if (!res.ok) return;
        const data = (await res.json()) as { skills?: SkillItem[] };
        if (!cancelled) setSkills(data.skills || []);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const items = useMemo(
    () =>
      skills
        .filter((s) => s.enabled)
        .map((s) => ({
          id: s.id,
          name: s.name,
          token: skillNameToToken(s.name),
        })),
    [skills],
  );

  return (
    <PickerPanelShell
      title="技能"
      groups={[{ id: "skills", items }]}
      inputValue={inputValue}
      onToggleItem={onToggleItem}
      renderTag={(item) => {
        const cls =
          RICH_SKILL_STYLE_CLASSES[
            hashSkillLabel(item.token) % RICH_SKILL_STYLE_CLASSES.length
          ];
        return (
          <span className={cn("rounded px-1 py-px text-xs font-medium", cls)}>
            {item.token}
          </span>
        );
      }}
      loading={loading}
      emptyLabel="暂无已启用的技能"
      emptyActionLabel="管理技能"
      onEmptyAction={() => {
        usePageTabStore.getState().setAgentsSection("skills");
        setHubTab("agents");
      }}
    />
  );
}

/** IMA wiki libraries from GET /api/ima/knowledge-bases. */
const IMA_CLIENT_ACCOUNT = "ima:client_id";
const IMA_KEY_ACCOUNT = "ima:api_key";

type KnowledgeBasePayload = {
  configured?: boolean;
  items?: { id?: string; name?: string }[];
  hint?: string;
};

function knowledgeItemsFromPayload(data: KnowledgeBasePayload | null): PickerItem[] {
  return (data?.items || [])
    .filter((row) => (row.id || "").trim() || (row.name || "").trim())
    .map((row) => {
      const id = String(row.id || "").trim();
      const name = String(row.name || "").trim() || id;
      return { id: id || name, name, token: id || name };
    });
}

async function hasImaKeys(): Promise<boolean> {
  if (!window.api?.getKey) return false;
  const [id, key] = await Promise.all([
    window.api.getKey(IMA_CLIENT_ACCOUNT),
    window.api.getKey(IMA_KEY_ACCOUNT),
  ]);
  return Boolean((id || "").trim() && (key || "").trim());
}

async function fetchKnowledgeBaseList(
  base: string,
): Promise<{ status: number; data: KnowledgeBasePayload | null }> {
  const res = await fetch(`${base.replace(/\/$/, "")}/api/ima/knowledge-bases`);
  try {
    return {
      status: res.status,
      data: (await res.json()) as KnowledgeBasePayload,
    };
  } catch {
    return { status: res.status, data: null };
  }
}

export function KnowledgePickerPanel({
  selected,
  onToggleItem,
}: {
  selected: BoundKnowledgeBase[];
  onToggleItem: (item: PickerItem) => void;
}) {
  const setHubTab = usePageTabStore((s) => s.setHubTab);
  const [items, setItems] = useState<PickerItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [configured, setConfigured] = useState(true);
  const [emptyHint, setEmptyHint] = useState("");

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const savedKeys = await hasImaKeys();
        let url = ((await window.api.getBackendUrl()) || "").replace(/\/$/, "");
        if (!url) {
          if (!cancelled) {
            setConfigured(savedKeys);
            setItems([]);
            setEmptyHint(savedKeys ? "后端未连接，请先启动应用后再打开。" : "");
          }
          return;
        }

        let { status, data } = await fetchKnowledgeBaseList(url);
        const needRestart =
          savedKeys &&
          (status === 404 || data?.configured === false);
        if (needRestart && window.api.restartBackend) {
          url = ((await window.api.restartBackend()) || url).replace(/\/$/, "");
          ({ status, data } = await fetchKnowledgeBaseList(url));
        }
        if (cancelled) return;
        const next = knowledgeItemsFromPayload(data);
        const ready =
          next.length > 0 || data?.configured !== false || savedKeys;
        setConfigured(ready);
        setItems(next);
        if (next.length > 0) {
          setEmptyHint("");
          return;
        }
        if (!savedKeys && data?.configured === false) {
          setEmptyHint("");
        } else if (status === 404) {
          setEmptyHint("无法加载知识库列表，请重启应用后再试。");
        } else if (data?.hint) {
          setEmptyHint(String(data.hint));
        } else if (savedKeys && data?.configured === false) {
          setEmptyHint(
            "凭证已保存在本机，但后端尚未加载。请到 Hub「知识库」点保存。",
          );
        } else {
          setEmptyHint("");
        }
      } catch {
        if (!cancelled) {
          setConfigured(false);
          setItems([]);
          setEmptyHint("无法加载知识库列表，请稍后重试。");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const selectedIds = useMemo(
    () => new Set(selected.map((row) => row.id || row.name)),
    [selected],
  );

  const emptyLabel =
    !configured && !emptyHint
      ? "尚未配置知识库"
      : emptyHint || "当前账号没有知识库";

  return (
    <PickerPanelShell
      title="知识库"
      groups={[{ id: "ima", label: "腾讯 ima", items }]}
      inputValue=""
      onToggleItem={onToggleItem}
      isSelected={(item) => selectedIds.has(item.id)}
      renderTag={() => (
        <span
          className={cn(
            "rounded px-1 py-px text-xs font-medium",
            RICH_CONNECTOR_STYLE_CLASSES,
          )}
        >
          ima
        </span>
      )}
      renderLogo={() => (
        <img
          src={getKnowledgeLogo("ima")}
          alt=""
          className="h-4 w-4 object-contain"
        />
      )}
      loading={loading}
      emptyLabel={emptyLabel}
      emptyActionLabel="管理知识库"
      onEmptyAction={() => setHubTab("knowledge")}
    />
  );
}
