/** Catalog of knowledge-base backends shown in Hub「知识库」. */

export type KnowledgeSourceId = "ima" | "ragflow" | "notion";

export type KnowledgeSourceGroup = "cloud" | "selfhost";

export interface KnowledgeSource {
  id: KnowledgeSourceId;
  name: string;
  group: KnowledgeSourceGroup;
  comingSoon: boolean;
  docsUrl?: string;
  description: string;
}

/** Composer-bound library; sent with each chat turn so search is default. */
export interface BoundKnowledgeBase {
  id: string;
  name: string;
  source: string;
}

export function parseBoundKnowledgeBases(raw: unknown): BoundKnowledgeBase[] {
  if (!Array.isArray(raw)) return [];
  const out: BoundKnowledgeBase[] = [];
  const seen = new Set<string>();
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const row = item as Record<string, unknown>;
    const id = String(row.id || "").trim();
    const name = String(row.name || "").trim();
    if (!id && !name) continue;
    const key = id || name;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({
      id,
      name: name || id,
      source: String(row.source || "ima").trim() || "ima",
    });
    if (out.length >= 8) break;
  }
  return out;
}

export const KNOWLEDGE_SOURCE_GROUPS: {
  id: KnowledgeSourceGroup;
  label: string;
}[] = [
  { id: "cloud", label: "云端知识库" },
  { id: "selfhost", label: "自托管" },
];

export const KNOWLEDGE_SOURCES: KnowledgeSource[] = [
  {
    id: "ima",
    name: "腾讯 ima",
    group: "cloud",
    comingSoon: false,
    docsUrl: "https://ima.qq.com/agent-interface",
    description: "填写 OpenAPI Client ID 与 API Key 后，Agent 即可检索和阅读知识库内容。",
  },
  {
    id: "notion",
    name: "Notion",
    group: "cloud",
    comingSoon: true,
    description: "Notion 知识库接入即将推出。",
  },
  {
    id: "ragflow",
    name: "RAGFlow",
    group: "selfhost",
    comingSoon: true,
    docsUrl: "https://github.com/infiniflow/ragflow",
    description: "自托管 RAGFlow 知识库接入即将推出。",
  },
];

export function knowledgeSourcesInGroup(
  group: KnowledgeSourceGroup,
): KnowledgeSource[] {
  return KNOWLEDGE_SOURCES.filter((s) => s.group === group);
}
