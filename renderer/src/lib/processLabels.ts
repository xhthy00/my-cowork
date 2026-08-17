/**
 * Chinese labels for live WorkLog / Progress / Context during a run.
 * Keep internal ids (browser_agent, fs.read) in SSE/payloads; localize only for UI.
 */

const AGENT_ZH: Record<string, string> = {
  coordinator: "任务协调",
  supervisor: "任务调度",
  single_agent: "单智能体",
  browser_agent: "浏览器智能体",
  developer_agent: "开发智能体",
  document_agent: "文档智能体",
  multi_modal_agent: "多模态智能体",
  web_worker: "浏览器智能体",
  file_worker: "开发智能体",
  doc_worker: "文档智能体",
  msg_worker: "多模态智能体",
};

/** Builtin / common tool ids → short Chinese action labels. */
const TOOL_ZH: Record<string, string> = {
  "list_skills": "列出技能",
  "load_skill": "加载技能",
  "fs.list": "列出文件",
  "fs.read": "读取文件",
  "fs.write": "写入文件",
  "fs.delete": "删除文件",
  "fs.mkdir": "创建目录",
  "exec.bash": "执行命令",
  "http.request": "网络请求",
  "notes.list": "列出笔记",
  "notes.create": "创建笔记",
  "notes.append": "追加笔记",
  "notes.read": "读取笔记",
  "notes.update": "更新笔记",
  "notes.delete": "删除笔记",
  "pptx.gen": "生成 PPT",
  "pptx_gen": "生成 PPT",
  "docx.gen": "生成 Word",
  "docx_gen": "生成 Word",
  "xlsx.gen": "生成 Excel",
  "xlsx_gen": "生成 Excel",
  "pdf.gen": "生成 PDF",
  "pdf_gen": "生成 PDF",
  "memory.search": "检索记忆",
  "memory.write": "写入记忆",
  "lark.send_message": "发送飞书消息",
};

const RUN_FINISH_RE =
  /^(Running|Finished)\s+([a-z0-9_]+)\s*$/i;
const RUN_FINISH_ZH_RE =
  /^(正在运行|已完成)\s*[·•\-]\s*([a-z0-9_]+)\s*$/i;

function normalizeKey(raw: string): string {
  return raw.trim().replace(/\s+/g, " ");
}

function toolLookupKey(tool: string): string {
  return tool
    .trim()
    .replace(/^builtin\./i, "")
    .replace(/\s+/g, ".")
    .replace(/_/g, ".")
    .toLowerCase();
}

/** Agent / graph node id → Chinese display name. */
export function humanizeAgent(agentId: string): string {
  const id = agentId.trim();
  if (!id) return "智能体";
  if (AGENT_ZH[id]) return AGENT_ZH[id];
  const snake = id.replace(/[\s-]+/g, "_").toLowerCase();
  if (AGENT_ZH[snake]) return AGENT_ZH[snake];
  return id.replace(/[_-]+/g, " ");
}

/** Tool id → Chinese action label. */
export function humanizeTool(tool: string): string {
  const t = normalizeKey(tool);
  if (!t) return "工具";

  const direct = TOOL_ZH[t] || TOOL_ZH[toolLookupKey(t)];
  if (direct) return direct;

  // Fuzzy: notes / fs / mcp family
  const key = toolLookupKey(t);
  if (key.includes("list.skill") || key === "list.skills") return "列出技能";
  if (key.includes("load.skill")) return "加载技能";
  if (key.startsWith("fs.") || /^fs\b/.test(key)) {
    if (key.includes("list")) return "列出文件";
    if (key.includes("read")) return "读取文件";
    if (key.includes("write")) return "写入文件";
    if (key.includes("delete") || key.includes("remove")) return "删除文件";
    return "文件操作";
  }
  if (key.startsWith("notes.") || key.includes("note")) {
    if (key.includes("list")) return "列出笔记";
    if (key.includes("create") || key.includes("add")) return "创建笔记";
    if (key.includes("append")) return "追加笔记";
    if (key.includes("read") || key.includes("get")) return "读取笔记";
    if (key.includes("update") || key.includes("edit")) return "更新笔记";
    return "笔记操作";
  }
  if (/pptx/i.test(t)) return "生成 PPT";
  if (/docx/i.test(t)) return "生成 Word";
  if (/xlsx/i.test(t)) return "生成 Excel";
  if (/pdf/i.test(t)) return "生成 PDF";
  if (/mcp|connector/i.test(t)) return t.replace(/[._]/g, " ");
  if (/skill/i.test(t)) return "技能操作";

  // Fallback: keep readable, avoid raw snake when possible
  return t.replace(/[._]/g, " ");
}

/**
 * Localize assign / status lines such as "Running browser_agent".
 * Non-matching content (e.g. Chinese todo text) is returned as-is.
 */
export function humanizeAssignContent(content: string, agentId?: string): string {
  const text = normalizeKey(content);
  if (!text) return agentId ? humanizeAgent(agentId) : "";

  const m = RUN_FINISH_RE.exec(text) || RUN_FINISH_ZH_RE.exec(text);
  if (m) {
    const status = m[1];
    const verb =
      /^(Finished|已完成)$/i.test(status) ? "已完成" : "正在运行";
    return `${verb} · ${humanizeAgent(m[2])}`;
  }

  // "browser_agent · …" style prefixes
  for (const id of Object.keys(AGENT_ZH)) {
    const re = new RegExp(`^${id}\\s*[·•\\-]\\s*`, "i");
    if (re.test(text)) {
      return text.replace(re, `${AGENT_ZH[id]} · `);
    }
  }

  return text;
}

/** WorkLog row: prefer Chinese agent + localized label. */
export function formatWorkLogLine(
  label: string,
  detail?: string,
): string {
  const localizedLabel = humanizeAssignContent(label, detail);
  if (!detail) return localizedLabel;

  // detail is often agent_id; if label already starts with same agent zh, don't duplicate
  const agentZh = humanizeAgent(detail);
  if (
    localizedLabel === agentZh ||
    localizedLabel.startsWith(`${agentZh} ·`) ||
    localizedLabel.startsWith("正在运行") ||
    localizedLabel.startsWith("已完成")
  ) {
    return localizedLabel;
  }
  // Avoid "browser_agent · 浏览器智能体"
  if (detail === label || humanizeAgent(label) === agentZh) {
    return agentZh;
  }
  return `${agentZh} · ${localizedLabel}`;
}
