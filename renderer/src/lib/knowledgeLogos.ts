import imaLogo from "@/assets/knowledge/ima.svg";
import notionLogo from "@/assets/knowledge/notion.svg";
import ragflowLogo from "@/assets/knowledge/ragflow.svg";

import type { KnowledgeSourceId } from "@/lib/knowledgeSources";

const KNOWLEDGE_LOGO_MAP: Record<KnowledgeSourceId, string> = {
  ima: imaLogo,
  ragflow: ragflowLogo,
  notion: notionLogo,
};

export function getKnowledgeLogo(id: KnowledgeSourceId): string {
  return KNOWLEDGE_LOGO_MAP[id];
}
