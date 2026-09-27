import type { Message } from "@/store/session";

type Question = NonNullable<Message["humanQuestion"]>;
type Field = NonNullable<Question["fields"]>[number];

export type FormField = Field & { description?: string };

type ParsedQuestion = {
  introduction: string;
  fields: FormField[];
};

const NUMBERED_ITEM = /(?:^|\n)[ \t]*(\d{1,2})[.、．)][ \t]*/g;

function referenceOptions(text: string): string[] {
  const reference = text.match(/选项参考[^\n：:]*[：:]([^\n]+)/);
  if (!reference) return [];
  return reference[1]
    .split(/[|｜]/)
    .map((value) => value.trim().replace(/^[A-Ga-g](?=[\s.、．:：-])[\s.、．:：-]*/, "").trim())
    .filter(Boolean);
}

/**
 * Older ask_human calls sometimes place a whole numbered questionnaire in
 * "question" instead of structured fields. Recover the numbered items so the
 * UI asks for each answer rather than showing one unrelated top-level choice.
 */
export function parseHumanQuestion(text: string): ParsedQuestion | null {
  const matches = [...text.matchAll(NUMBERED_ITEM)];
  if (matches.length < 2 || matches[0][1] !== "1") return null;
  const contiguous = matches.every((match, index) => Number(match[1]) === index + 1);
  if (!contiguous) return null;

  const introduction = text.slice(0, matches[0].index).trim();
  const firstOptions = referenceOptions(text);
  const fields = matches.map((match, index): FormField => {
    const start = (match.index ?? 0) + match[0].length;
    const end = index + 1 < matches.length ? matches[index + 1].index ?? text.length : text.length;
    let body = text.slice(start, end).trim();
    if (index === matches.length - 1) {
      body = body.split(/(?:^|\n)[ \t]*选项参考/)[0].trim();
    }

    const boldTitle = body.match(/^\*\*([^*]+)\*\*[ \t]*/);
    const plainTitle = !boldTitle ? body.match(/^([^\n：:]{1,24})[：:][ \t]*/) : null;
    const label = (boldTitle?.[1] ?? plainTitle?.[1] ?? `问题 ${index + 1}`).trim();
    let description = body.slice((boldTitle ?? plainTitle)?.[0].length ?? 0).trim();
    description = description.replace(/^[：:][ \t]*/, "").trim();

    let options: string[] = [];
    if (index === 0) {
      options = firstOptions;
      if (options.length) description = description.split(/例如[—–-]{1,2}/)[0].trim();
    } else if (/语气|风格/.test(label) && /正式公函/.test(description) && /商务简洁/.test(description)) {
      options = ["正式公函", "商务简洁", "亲切友好"];
      description = "";
    } else if (/交付|形式|格式/.test(label) && /邮件正文/.test(description) && /写成文件/.test(description)) {
      options = /HTML|Markdown|Word/i.test(description)
        ? ["直接给邮件正文", "HTML 文件", "Markdown 文件", "Word 文件"]
        : ["直接给邮件正文", "写成文件"];
    }

    return {
      label,
      kind: options.length ? "single" : "text",
      options,
      required: index === 0,
      description,
    };
  });

  if (fields.some((field) => !field.label)) return null;
  return { introduction, fields };
}
