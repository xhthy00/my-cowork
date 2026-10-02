import { useEffect, useRef, useState, type ReactNode } from "react";
import { Bot, Check, Feather, Hammer, Link2, Paperclip, Plus, Search, Settings, Upload, X } from "lucide-react";
import { apiFetch } from "@/api/backend";
import { importSkillZip } from "@/api/skills";
import { useCompactLayout } from "@/hooks/useCompactLayout";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuPortal,
  DropdownMenuSeparator, DropdownMenuSub, DropdownMenuSubContent, DropdownMenuSubTrigger, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { SkillItem } from "@/components/skills/SkillListItem";
import type { AssistantItem } from "@/components/hub/AssistantsView";
import { ensureActiveSession, useSessionsStore } from "@/store/sessions";
import { usePageTabStore } from "@/store/pageTab";
import { useWorkforceStore } from "@/store/workforce";
import { SessionMode } from "@/types/workforce";
import { connectorNameToToken, skillNameToToken, type PickerItem } from "./PickerPanel";

interface CatalogItem extends PickerItem { description: string }
interface Props {
  disabled?: boolean;
  modeInteractive: boolean;
  inputValue: string;
  onAddFiles: () => void;
  onToggleItem: (item: PickerItem) => void;
  onKnowledge: () => void;
  onIndustry: () => void;
  onFocusInput: () => void;
}

function SearchableCatalog({ title, icon, items, loading, error, selected, onSelect, children }: {
  title: string; icon: ReactNode; items: CatalogItem[]; loading: boolean; error?: string;
  selected?: (item: CatalogItem) => boolean; onSelect: (item: CatalogItem) => void; children?: ReactNode;
}) {
  const compact = useCompactLayout();
  const [query, setQuery] = useState("");
  const container = useRef<HTMLDivElement>(null);
  const filtered = items.filter(item => `${item.name} ${item.description}`.toLowerCase().includes(query.trim().toLowerCase()));
  return (
    <DropdownMenuSub onOpenChange={open => { if (!open) setQuery(""); }}>
      <DropdownMenuSubTrigger>{icon}{title}</DropdownMenuSubTrigger>
      <DropdownMenuPortal>
        <DropdownMenuSubContent ref={container} className="composer-add-submenu" sideOffset={compact ? -196 : 4} collisionPadding={12}>
          <label className="composer-menu-search">
            <Search size={16} aria-hidden />
            <input aria-label={`搜索${title}`} placeholder={`搜索${title}`} value={query} onChange={event => setQuery(event.target.value)} onKeyDown={event => {
              if (event.key === "Escape") return;
              event.stopPropagation();
              if (event.key === "ArrowDown") {
                event.preventDefault();
                container.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
              }
            }} />
          </label>
          <div className="composer-menu-results">
            {loading ? <p role="status" className="composer-menu-empty">正在加载…</p>
              : error ? <p role="alert" className="composer-menu-empty">{error}</p>
              : !filtered.length ? <p className="composer-menu-empty">{query ? "没有匹配结果" : `暂无可用${title}`}</p>
              : filtered.map((item, index) => (
                <DropdownMenuItem key={item.id} className="composer-catalog-item" onSelect={() => onSelect(item)}>
                  <span className="composer-item-mark" data-tone={index % 4} aria-hidden>{item.name.slice(0, 1).toUpperCase()}</span>
                  <span className="composer-item-copy"><span>{item.name}</span><small>{item.description || item.token}</small></span>
                  {selected?.(item) && <Check size={15} aria-hidden />}
                </DropdownMenuItem>
              ))}
          </div>
          {children && <><DropdownMenuSeparator />{children}</>}
        </DropdownMenuSubContent>
      </DropdownMenuPortal>
    </DropdownMenuSub>
  );
}

export default function ComposerAddMenu({ disabled, modeInteractive, inputValue, onAddFiles, onToggleItem, onKnowledge, onIndustry, onFocusInput }: Props) {
  const compact = useCompactLayout();
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [skills, setSkills] = useState<SkillItem[]>([]);
  const [assistants, setAssistants] = useState<AssistantItem[]>([]);
  const [connectors, setConnectors] = useState<CatalogItem[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [importStatus, setImportStatus] = useState("");
  const [revision, setRevision] = useState(0);
  const fileRef = useRef<HTMLInputElement>(null);
  const focusInputOnClose = useRef(false);
  const mode = useWorkforceStore(s => s.sessionMode);
  const boundAssistantId = useSessionsStore(s => s.sessions.find(project => project.id === s.activeId)?.assistantId);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setErrors({});
    void (async () => {
      try {
        const base = await window.api.getBackendUrl();
        if (!base) throw new Error("后端未连接");
        async function read<T>(path: string): Promise<T> {
          const response = await apiFetch(`${base}${path}`);
          if (!response.ok) throw new Error(`加载失败 ${response.status}`);
          return response.json();
        }
        const results = await Promise.allSettled([
          read<{ skills?: SkillItem[] }>("/api/skills"),
          read<{ assistants?: AssistantItem[] }>("/api/assistants"),
          read<{ mcpServers?: Record<string, { enabled?: boolean; description?: string }> }>("/api/mcp/servers"),
        ]);
        if (cancelled) return;
        const [skillResult, assistantResult, connectorResult] = results;
        if (skillResult.status === "fulfilled") setSkills(skillResult.value.skills || []);
        if (assistantResult.status === "fulfilled") setAssistants(assistantResult.value.assistants || []);
        if (connectorResult.status === "fulfilled") setConnectors(Object.entries(connectorResult.value.mcpServers || {}).filter(([, config]) => config.enabled !== false).map(([name, config]) => ({ id: name, name, token: connectorNameToToken(name), description: config.description || "MCP 连接器" })));
        const nextErrors: Record<string, string> = {};
        results.forEach((result, index) => { if (result.status === "rejected") nextErrors[["skills", "assistants", "connectors"][index]] = result.reason instanceof Error ? result.reason.message : "无法加载，请重试"; });
        setErrors(nextErrors);
      } catch (error) {
        if (!cancelled) {
          const message = error instanceof Error ? error.message : "无法加载，请重试";
          setErrors({ skills: message, assistants: message, connectors: message });
        }
      } finally { if (!cancelled) setLoading(false); }
    })();
    return () => { cancelled = true; };
  }, [open, revision]);

  function selectToken(item: CatalogItem) {
    focusInputOnClose.current = true;
    onToggleItem(item);
  }
  function manageSkills() {
    usePageTabStore.getState().setHubTab("agents");
    usePageTabStore.getState().setAgentsSection("skills");
  }
  async function importLocalSkill(file: File) {
    setImportStatus("正在导入技能…");
    try {
      await importSkillZip(file);
      setImportStatus("技能已导入");
      setRevision(value => value + 1);
    } catch (error) { setImportStatus(error instanceof Error ? error.message : "导入失败"); }
    setOpen(true);
  }
  const skillItems = skills.filter(skill => skill.enabled).map(skill => ({ id: skill.id, name: skill.appOrigin ? `${skill.name} · ${skill.appOrigin.name}` : skill.name, token: skillNameToToken(skill.appOrigin ? skill.id : skill.name), description: skill.description }));
  const assistantItems = assistants.map(assistant => ({ id: assistant.id, name: assistant.name, token: assistant.id, description: assistant.description }));
  return (
    <>
      <input ref={fileRef} type="file" accept=".zip" hidden aria-label="导入本地技能 ZIP" onChange={event => {
        const file = event.target.files?.[0];
        event.target.value = "";
        if (file) void importLocalSkill(file);
      }} />
      <DropdownMenu open={open} onOpenChange={setOpen}>
        <DropdownMenuTrigger asChild><button type="button" className="chat-add" aria-label={open ? "关闭添加菜单" : "添加内容"} title="添加内容" disabled={disabled}>{open ? <X size={20} aria-hidden /> : <Plus size={20} aria-hidden />}</button></DropdownMenuTrigger>
        <DropdownMenuContent className="composer-add-menu" side="top" align="start" sideOffset={8} collisionPadding={12} onCloseAutoFocus={event => {
          if (focusInputOnClose.current) {
            event.preventDefault();
            focusInputOnClose.current = false;
            onFocusInput();
          }
        }}>
          <DropdownMenuSub>
            <DropdownMenuSubTrigger><Paperclip aria-hidden />添加文件</DropdownMenuSubTrigger>
            <DropdownMenuPortal><DropdownMenuSubContent className="composer-add-file-menu" sideOffset={compact ? -196 : 4} collisionPadding={12}>
              <DropdownMenuItem onSelect={onAddFiles}><Paperclip aria-hidden />添加文件或照片</DropdownMenuItem>
              <DropdownMenuItem onSelect={onKnowledge}><Link2 aria-hidden />关联知识库</DropdownMenuItem>
            </DropdownMenuSubContent></DropdownMenuPortal>
          </DropdownMenuSub>
          <DropdownMenuSeparator />
          <DropdownMenuSub>
            <DropdownMenuSubTrigger><Feather aria-hidden />模式</DropdownMenuSubTrigger>
            <DropdownMenuPortal><DropdownMenuSubContent className="composer-add-file-menu" sideOffset={compact ? -196 : 4} collisionPadding={12}>
              {[{ id: SessionMode.SINGLE_AGENT, name: "单智能体" }, { id: SessionMode.WORKFORCE, name: "多智能体" }].map(item => <DropdownMenuItem key={item.id} disabled={!modeInteractive} onSelect={() => useWorkforceStore.getState().setSessionMode(item.id)}><span className="flex-1">{item.name}</span>{mode === item.id && <Check size={16} aria-hidden />}</DropdownMenuItem>)}
            </DropdownMenuSubContent></DropdownMenuPortal>
          </DropdownMenuSub>
          <SearchableCatalog title="专家" icon={<Bot aria-hidden />} items={assistantItems} loading={loading} error={errors.assistants} selected={item => item.id === boundAssistantId} onSelect={item => {
            const assistant = assistants.find(value => value.id === item.id);
            if (!assistant) return;
            useSessionsStore.getState().touchSession(ensureActiveSession(), { assistantId: assistant.id, assistantName: assistant.name, enabledSkillIds: assistant.enabled_skills, assistantPrompts: assistant.prompts });
            focusInputOnClose.current = true;
          }} />
          <SearchableCatalog title="技能" icon={<Hammer aria-hidden />} items={skillItems} loading={loading} error={errors.skills} selected={item => inputValue.includes(item.token)} onSelect={selectToken}>
            <DropdownMenuItem onSelect={() => fileRef.current?.click()}><Upload aria-hidden />从本地添加技能</DropdownMenuItem>
            <DropdownMenuItem onSelect={manageSkills}><Settings aria-hidden />管理技能</DropdownMenuItem>
            <DropdownMenuItem onSelect={onIndustry}><Hammer aria-hidden />行业工作台工具</DropdownMenuItem>
          </SearchableCatalog>
          <SearchableCatalog title="连接器" icon={<Link2 aria-hidden />} items={connectors} loading={loading} error={errors.connectors} selected={item => inputValue.includes(item.token)} onSelect={selectToken}>
            <DropdownMenuItem onSelect={() => usePageTabStore.getState().setHubTab("connectors")}><Settings aria-hidden />管理连接器</DropdownMenuItem>
          </SearchableCatalog>
          {importStatus && <p role="status" className="composer-menu-empty">{importStatus}</p>}
        </DropdownMenuContent>
      </DropdownMenu>
    </>
  );
}
