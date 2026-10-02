import { ArrowRight, Check, ChevronLeft, ChevronRight, Copy, Loader2, Pencil, X } from "lucide-react";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import ReactMarkdown from "react-markdown";

import { submitHumanReply } from "@/api/humanReply";
import type { Message } from "@/store/session";
import { useSessionsStore } from "@/store/sessions";
import MarkdownView from "./markdown/MarkdownView";
import { parseHumanQuestion, type FormField } from "./parseHumanQuestion";
import "./HumanQuestionCard.css";

type Question = NonNullable<Message["humanQuestion"]>;

function InlineMarkdown({ text }: { text: string }) {
  return <ReactMarkdown components={{ p: ({ children }) => <>{children}</>, a: ({ children }) => <>{children}</> }}>{text}</ReactMarkdown>;
}

function questionContent(question: Question, text: string) {
  const parsed = parseHumanQuestion(text);
  const fields: FormField[] = question.fields?.length ? question.fields : parsed?.fields.length ? parsed.fields
    : question.options.length ? [{ label: "请选择或自行填写", kind: "single", options: question.options, required: true }]
    : [{ label: "你的回复", kind: "text", options: [], required: true, placeholder: "请填写你的想法或补充信息" }];
  return { fields, introduction: parsed?.introduction ?? text, structured: Boolean(question.fields?.length || parsed) };
}

/** The timeline keeps the context; the questionnaire lives beside the composer. */
export function HumanQuestionSummary({ question, text }: { question: Question; text: string }) {
  const { fields, introduction } = questionContent(question, text);
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState("");
  if (question.status === "answered" && question.answer) {
    const lines = question.answer.split("\n");
    const entries: Array<{ label: string; value: string }> = [];
    let complete = true;
    for (const line of lines) {
      const match = fields.map((field, index) => ({ field, prefix: `${index + 1}. ${field.label}：` })).find(({ prefix }) => line.startsWith(prefix));
      if (match) entries.push({ label: match.field.label, value: line.slice(match.prefix.length) });
      else if (entries.length) entries[entries.length - 1].value += `\n${line}`;
      else { complete = false; break; }
    }
    return <section className="human-question-record" aria-label="已补充的信息">
      <header>
        <Check size={16} aria-hidden="true" />
        <h3>补充信息</h3><span role="status">已回复</span>
        <button type="button" aria-label={copied ? "已复制补充信息" : "复制补充信息"} onClick={async () => {
          try { await navigator.clipboard.writeText(question.answer!); setCopied(true); setCopyError(""); }
          catch { setCopyError("复制失败，请重试"); }
        }}>{copied ? <Check size={15} /> : <Copy size={15} />}</button>
      </header>
      {complete && entries.length ? <dl>{entries.map((entry, i) => <div key={i}><dt><InlineMarkdown text={entry.label} /></dt><dd>{entry.value}</dd></div>)}</dl>
        : <div className="human-question-record__answer">{question.answer}</div>}
      {introduction && <details><summary>查看提问说明</summary><MarkdownView>{introduction}</MarkdownView></details>}
      {copyError && <p role="alert" className="human-question-field__error">{copyError}</p>}
    </section>;
  }
  return <div className="human-question-summary" data-status={question.status}>
    {introduction && (introduction.length > 500
      ? <details><summary>查看问题说明</summary><MarkdownView>{introduction}</MarkdownView></details>
      : <MarkdownView>{introduction}</MarkdownView>)}
    <p role="status">{question.status === "pending" ? `等待你的回答 · ${fields.length} 个问题` : question.status === "answered" ? "已回复，继续处理任务" : "提问已结束"}</p>
  </div>;
}

export default function HumanQuestionCard({ question, text, projectId: boundProjectId, hidden = false, onClose }: {
  question: Question; text: string; projectId?: string; hidden?: boolean; onClose?: () => void;
}) {
  const activeId = useSessionsStore((s) => s.activeId);
  const projectId = boundProjectId || activeId;
  const formId = useId();
  const fieldRef = useRef<HTMLFieldSetElement>(null);
  const focusInvalid = useRef(false);
  const wasHidden = useRef(hidden);
  const [index, setIndex] = useState(0);
  const [selected, setSelected] = useState<Record<number, string[]>>({});
  const [customSelected, setCustomSelected] = useState<Record<number, boolean>>({});
  const [customValues, setCustomValues] = useState<Record<number, string>>({});
  const [errors, setErrors] = useState<Record<number, string>>({});
  const [formError, setFormError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const { fields, structured } = questionContent(question, text);
  const field = fields[index];
  const isLast = index === fields.length - 1;
  const choiceField = field.kind !== "text" && field.options.length > 0;
  const isCustom = Boolean(customSelected[index]);
  const title = !structured && text.length < 120 ? text : field.label;

  useEffect(() => {
    if (wasHidden.current && !hidden) {
      fieldRef.current?.querySelector<HTMLElement>("input, textarea")?.focus({ preventScroll: true });
    }
    wasHidden.current = hidden;
  }, [hidden]);

  useEffect(() => {
    if (!focusInvalid.current || hidden) return;
    focusInvalid.current = false;
    fieldRef.current?.querySelector<HTMLElement>(customSelected[index] ? "textarea" : "input, textarea")?.focus({ preventScroll: true });
  }, [index, errors, hidden, customSelected]);

  function valuesFor(i: number, overrides?: { skip: number }) {
    if (overrides?.skip === i) return [];
    const typed = (customValues[i] ?? "").trim();
    const f = fields[i];
    return f.kind === "text" || !f.options.length ? (typed ? [typed] : [])
      : [...(selected[i] ?? []), ...(customSelected[i] && typed ? [typed] : [])];
  }

  function errorFor(i: number) {
    if (customSelected[i] && !(customValues[i] ?? "").trim()) return "请填写自定义内容";
    if (fields[i].required && !valuesFor(i).length) return "请回答这一项";
    return "";
  }

  function showError(i: number, error: string) {
    focusInvalid.current = true;
    setIndex(i);
    setErrors((previous) => ({ ...previous, [i]: error }));
  }

  function moveNext() {
    const error = errorFor(index);
    if (error) { showError(index, error); return; }
    setFormError("");
    setIndex((current) => Math.min(current + 1, fields.length - 1));
  }

  async function submit(skip?: number) {
    if (!projectId || submitting || question.status !== "pending") return;
    const answers: string[] = [];
    for (let i = 0; i < fields.length; i++) {
      const error = skip === i ? "" : errorFor(i);
      if (error) { showError(i, error); return; }
      const values = valuesFor(i, skip === undefined ? undefined : { skip });
      if (values.length) answers.push((i + 1) + ". " + fields[i].label + "：" + values.join("；"));
    }
    setSubmitting(true);
    setFormError("");
    try {
      await submitHumanReply(projectId, question.task_id, question.question_id,
        answers.length ? answers.join("\n") : "暂不补充，请根据已有信息继续处理，不确定的信息请标注待确认。");
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "回复失败，请重试");
    } finally { setSubmitting(false); }
  }

  function skipCurrent() {
    setSelected((previous) => ({ ...previous, [index]: [] }));
    setCustomSelected((previous) => ({ ...previous, [index]: false }));
    setCustomValues((previous) => ({ ...previous, [index]: "" }));
    setErrors((previous) => ({ ...previous, [index]: "" }));
    if (isLast) void submit(index);
    else setIndex(index + 1);
  }

  function choose(option: string) {
    setSelected((previous) => {
      const current = previous[index] ?? [];
      return { ...previous, [index]: field.kind === "single" ? [option] : current.includes(option) ? current.filter(value => value !== option) : [...current, option] };
    });
    if (field.kind === "single") setCustomSelected((previous) => ({ ...previous, [index]: false }));
    setErrors((previous) => ({ ...previous, [index]: "" }));
  }

  if (question.status !== "pending") return <HumanQuestionSummary question={question} text={text} />;

  function choice(text: string, position: number, custom = false) {
    const active = custom ? isCustom : (selected[index] ?? []).includes(text);
    return <label key={custom ? "custom" : position} className="human-question-choice" data-selected={active}>
      <input className="sr-only" type={field.kind === "multiple" ? "checkbox" : "radio"}
        name={formId + "-field-" + index} checked={active} disabled={submitting}
        onChange={() => {
          if (!custom) { choose(text); return; }
          setCustomSelected((previous) => ({ ...previous, [index]: !isCustom }));
          if (field.kind === "single") setSelected((previous) => ({ ...previous, [index]: [] }));
          setErrors((previous) => ({ ...previous, [index]: "" }));
        }} />
      <span className="human-question-choice__number" aria-hidden="true">{custom ? <Pencil size={15} /> : field.kind === "multiple" && active ? <Check size={15} /> : position + 1}</span>
      <span className="human-question-choice__text"><InlineMarkdown text={text} /></span>
      {active && !custom && <ArrowRight className="human-question-choice__arrow" size={17} aria-hidden="true" />}
    </label>;
  }

  return <section className="human-question-card" data-status="pending" aria-label="代理提问" hidden={hidden} aria-busy={submitting}>
    <header className="human-question-card__header">
      <h3 id={formId + "-title"} className="human-question-field__title" aria-live="polite"><InlineMarkdown text={title || field.label} /></h3>
      <div className="human-question-card__navigation" aria-label="切换问题">
        <button type="button" aria-label="上一题" disabled={index === 0 || submitting} onClick={() => setIndex(index - 1)}><ChevronLeft size={17} /></button>
        <span aria-label={`第 ${index + 1} 题，共 ${fields.length} 题`}>{index + 1}/{fields.length}</span>
        <button type="button" aria-label="下一题" disabled={isLast || submitting} onClick={moveNext}><ChevronRight size={17} /></button>
        {onClose && <button type="button" aria-label="收起补全问题" disabled={submitting} onClick={onClose}><X size={18} /></button>}
      </div>
    </header>
    <form noValidate onSubmit={(event: FormEvent) => { event.preventDefault(); if (isLast) void submit(); else moveNext(); }}>
      <div className="human-question-card__body">
        <fieldset ref={fieldRef} key={index} className="human-question-field" aria-labelledby={formId + "-title"} aria-describedby={errors[index] ? formId + "-error" : undefined}>
          {field.description && <div className="human-question-field__description"><MarkdownView>{field.description}</MarkdownView></div>}
          {choiceField && <div className="human-question-field__choices">
            {field.options.map((option, position) => choice(option, position))}
            {choice("自己填写", field.options.length, true)}
          </div>}
          {(!choiceField || isCustom) && <textarea
            rows={2} aria-label={choiceField ? field.label + "：自定义内容" : field.label}
            aria-invalid={Boolean(errors[index])} className="human-question-field__input"
            placeholder={field.placeholder || "其他补充…"} value={customValues[index] ?? ""} disabled={submitting}
            onChange={(event) => { setCustomValues((previous) => ({ ...previous, [index]: event.target.value })); setErrors((previous) => ({ ...previous, [index]: "" })); }} />}
          {errors[index] && <p id={formId + "-error"} className="human-question-field__error" role="alert">{errors[index]}</p>}
          {formError && <p className="human-question-field__error" role="alert">{formError}</p>}
        </fieldset>
      </div>
      <footer className="human-question-card__footer">
        <span className="human-question-card__hint">{field.required ? "必填" : "选填"}{field.kind === "multiple" ? " · 可多选" : ""}</span>
        <div className="human-question-card__actions">
          {!field.required && <button type="button" className="human-question-card__skip" disabled={submitting} onClick={skipCurrent}>跳过</button>}
          <button type="submit" disabled={submitting} className="human-question-card__submit">
            {submitting && <Loader2 size={15} className="animate-spin" aria-hidden="true" />}
            {isLast ? "提交并继续" : "下一步"}{!isLast && <ChevronRight size={15} aria-hidden="true" />}
          </button>
        </div>
      </footer>
    </form>
  </section>;
}
