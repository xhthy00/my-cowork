/**
 * Mid-run status talk is not the final answer (WorkBuddy: only the end card
 * is in the bubble; process lives in WorkLog).
 *
 * Catch first-person "I will search / I have enough / now writing" sentences
 * whether they start with 让我, 我先梳理, 我已经搜集, etc.
 */

const PROCESS_SENTENCE_RE =
  /^(?:我来帮你|我将(?:开始|先)|让我|我先|我已经|现在(?:让我|整理|撰写|搜索|开始)|接下来|继续|开始调研|制定计划|然后(?:搜索|整理|查询|把)|搜集到足够|正在(?:整理|撰写|搜索|查询)|The user is asking|Let me |I (?:need|will|have|should) )/i;

export function splitSentences(text: string): string[] {
  return text
    .split(/(?<=[。！？])/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export function isProcessSentence(text: string): boolean {
  const t = text.trim();
  return Boolean(t) && PROCESS_SENTENCE_RE.test(t);
}

const MARKDOWN_LINE_RE =
  /^\s{0,3}(?:#{1,6}\s|>\s|[-*+]\s|\d+[.)]\s|\|)/;

/** Drop status sentences; keep a real report if one follows. */
export function stripProcessNarration(text: string): string {
  const t = text.trim();
  if (!t) return "";
  const out: string[] = [];
  for (const line of t.split("\n")) {
    if (!line.trim()) {
      out.push("");
      continue;
    }
    // Tables / headings / lists must keep their line breaks (join("") was
    // collapsing `| a |` + `| --- |` into `| a || --- |`).
    if (MARKDOWN_LINE_RE.test(line)) {
      out.push(line);
      continue;
    }
    const kept = line.split(/(?<=[。！？])/).filter((s) => !isProcessSentence(s));
    if (kept.length) out.push(kept.join(""));
  }
  return out.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

export function isProcessNarration(text: string): boolean {
  const t = text.trim();
  if (!t) return false;
  return stripProcessNarration(t) === "";
}

/**
 * WorkBuddy-style: only structured / conclusive text belongs in the bubble.
 * Tool talk and "now I will write the report" stay hidden until this is true.
 */
export function looksLikeFinalAnswer(text: string): boolean {
  const t = stripProcessNarration(text);
  if (!t) return false;
  if (/^#{1,3}\s/m.test(t)) return true;
  if (/^\|.+\|/m.test(t) && /\|[-: ]+\|/.test(t)) return true;
  if (/^[一二三四五六七八九十]+[、．.]/m.test(t)) return true;
  if (/<(?:h[1-6]|table|article)\b/i.test(t)) return true;
  if (/(?:调研报告已生成|核心要点摘要|政策要点)/.test(t) && t.length > 40) return true;
  if (/(?:我先|让我|我已经|现在整理|撰写最终|梳理任务)/.test(t) && t.length < 500) {
    return false;
  }
  return t.length >= 80;
}
