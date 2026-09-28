import { Check, CircleHelp, Loader2, Send } from "lucide-react";
import { useId, useRef, useState, type FormEvent } from "react";
import ReactMarkdown from "react-markdown";

import { submitHumanReply } from "@/api/humanReply";
import type { Message } from "@/store/session";
import { useSessionsStore } from "@/store/sessions";
import MarkdownView from "./markdown/MarkdownView";
import { parseHumanQuestion, type FormField } from "./parseHumanQuestion";
import "./HumanQuestionCard.css";

type Question = NonNullable<Message["humanQuestion"]>;
type Field = FormField;

function InlineMarkdown({ text }: { text: string }) {
  return (
    <ReactMarkdown components={{ p: ({ children }) => <>{children}</>, a: ({ children }) => <>{children}</> }}>
      {text}
    </ReactMarkdown>
  );
}

function Choice({
  active,
  disabled,
  kind,
  name,
  text,
  onChange,
}: {
  active: boolean;
  disabled: boolean;
  kind: "single" | "multiple";
  name: string;
  text: string;
  onChange: () => void;
}) {
  return (
    <label className="human-question-choice" data-selected={active} data-kind={kind}>
      <input
        className="sr-only"
        type={kind === "single" ? "radio" : "checkbox"}
        name={name}
        checked={active}
        disabled={disabled}
        onChange={onChange}
      />
      <span className="human-question-choice__marker" aria-hidden="true">
        {active && (kind === "single" ? <span className="human-question-choice__dot" /> : <Check size={13} strokeWidth={2.8} />)}
      </span>
      <span className="human-question-choice__text"><InlineMarkdown text={text} /></span>
    </label>
  );
}

export default function HumanQuestionCard({ question, text }: { question: Question; text: string }) {
  const projectId = useSessionsStore((s) => s.activeId);
  const formId = useId();
  const fieldRefs = useRef<Record<number, HTMLFieldSetElement | null>>({});
  const [selected, setSelected] = useState<Record<number, string[]>>({});
  const [customSelected, setCustomSelected] = useState<Record<number, boolean>>({});
  const [customValues, setCustomValues] = useState<Record<number, string>>({});
  const [errors, setErrors] = useState<Record<number, string>>({});
  const [formError, setFormError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [questionExpanded, setQuestionExpanded] = useState(!question.fields?.length);

  const parsed = parseHumanQuestion(text);
  const displayText = parsed?.introduction ?? text;
  const fields: Field[] = question.fields?.length
    ? question.fields
    : parsed?.fields.length
      ? parsed.fields
      : question.options.length
        ? [{ label: "请选择或自行填写", kind: "single", options: question.options, required: true }]
        : [{ label: "你的回复", kind: "text", options: [], required: true, placeholder: "请填写你的想法或补充信息" }];

  const answeredCount = fields.reduce((count, field, index) => {
    const typed = (customValues[index] ?? "").trim();
    const hasAnswer = field.kind === "text" || !field.options.length
      ? Boolean(typed)
      : Boolean(selected[index]?.length) || (Boolean(customSelected[index]) && Boolean(typed));
    return count + Number(hasAnswer);
  }, 0);

  function chooseOption(index: number, field: Field, option: string) {
    setSelected((previous) => {
      const current = previous[index] ?? [];
      return {
        ...previous,
        [index]: field.kind === "single"
          ? [option]
          : current.includes(option) ? current.filter((item) => item !== option) : [...current, option],
      };
    });
    if (field.kind === "single") setCustomSelected((previous) => ({ ...previous, [index]: false }));
    setErrors((previous) => ({ ...previous, [index]: "" }));
    setFormError("");
  }

  function chooseCustom(index: number, field: Field) {
    const next = !customSelected[index];
    setCustomSelected((previous) => ({ ...previous, [index]: next }));
    if (field.kind === "single") setSelected((previous) => ({ ...previous, [index]: [] }));
    setErrors((previous) => ({ ...previous, [index]: "" }));
    setFormError("");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!projectId || submitting || question.status !== "pending") return;

    const nextErrors: Record<number, string> = {};
    const answers: string[] = [];
    fields.forEach((field, index) => {
      const typed = (customValues[index] ?? "").trim();
      const chosen = selected[index] ?? [];
      const values = field.kind === "text" || !field.options.length
        ? (typed ? [typed] : [])
        : [...chosen, ...(customSelected[index] && typed ? [typed] : [])];
      if (customSelected[index] && !typed) nextErrors[index] = "请填写自定义内容";
      else if (field.required && !values.length) nextErrors[index] = "请回答这一项";
      if (values.length) answers.push((index + 1) + ". " + field.label + "：" + values.join("；"));
    });
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) {
      const first = Number(Object.keys(nextErrors)[0]);
      fieldRefs.current[first]?.querySelector<HTMLElement>(customSelected[first] ? "textarea" : "input, textarea")?.focus();
      return;
    }
    if (!answers.length) {
      setFormError("请至少回答一项");
      return;
    }

    setSubmitting(true);
    setFormError("");
    try {
      await submitHumanReply(projectId, question.task_id, question.question_id, answers.join("\n"));
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "回复失败，请重试");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="human-question-card" data-status={question.status} aria-label="代理提问">
      <header className="human-question-card__header">
        <span className="human-question-card__icon"><CircleHelp size={19} strokeWidth={2} aria-hidden="true" /></span>
        <div className="human-question-card__heading">
          <h3>{question.status === "pending" ? "需要你的决定" : question.status === "answered" ? "已回复" : "提问已结束"}</h3>
          <p>{question.status === "pending" ? "补充关键信息后，任务将继续执行" : question.status === "answered" ? "这次提问已处理" : "原任务已结束。可在下方继续说明需求，重新开始处理。"}</p>
        </div>
        {question.status === "pending" && (
          <span className="human-question-card__status">
            <span className="human-question-card__status-dot" aria-hidden="true" />
            等待回复
          </span>
        )}
      </header>

      {question.status === "pending" && fields.length > 1 && (
        <div className="human-question-card__progress">
          <div className="human-question-card__progress-label">
            <span>填写进度</span>
            <strong>{answeredCount} / {fields.length}</strong>
          </div>
          <div className="human-question-card__progress-track" role="progressbar" aria-label="填写进度" aria-valuemin={0} aria-valuemax={fields.length} aria-valuenow={answeredCount}>
            <span className="human-question-card__progress-fill" style={{ width: (answeredCount / fields.length * 100) + "%" }} />
          </div>
        </div>
      )}

      <div className="human-question-card__body">
        <div className="human-question-card__intro">
          {displayText.length > 500 ? (
            <details open={questionExpanded} onToggle={(event) => setQuestionExpanded(event.currentTarget.open)}>
              <summary>{questionExpanded ? "收起完整问题" : "查看完整问题"}</summary>
              <MarkdownView>{displayText}</MarkdownView>
            </details>
          ) : displayText ? (
            <MarkdownView>{displayText}</MarkdownView>
          ) : (
            <span>请填写以下信息后继续。</span>
          )}
        </div>

        {question.status === "pending" && (
          <form onSubmit={(event) => void submit(event)} noValidate>
            <div>
              {fields.map((field, index) => {
                const chosen = selected[index] ?? [];
                const isCustom = Boolean(customSelected[index]);
                const choiceField = field.kind !== "text" && field.options.length > 0;
                const choiceName = formId + "-field-" + index;
                return (
                  <fieldset
                    key={index}
                    ref={(element) => { fieldRefs.current[index] = element; }}
                    className="human-question-field"
                    aria-describedby={errors[index] ? formId + "-error-" + index : undefined}
                  >
                    <legend className="sr-only"><InlineMarkdown text={field.label} /></legend>
                    <div className="human-question-field__head">
                      <span className="human-question-field__number" aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
                      <span className="human-question-field__title"><InlineMarkdown text={field.label} /></span>
                      <span className="human-question-field__badge" data-required={field.required}>{field.required ? "必填" : "选填"}</span>
                    </div>
                    <div className="human-question-field__content">
                      {field.description && <div className="human-question-field__description"><MarkdownView>{field.description}</MarkdownView></div>}
                      {choiceField ? (
                        <>
                          <div className="human-question-field__choices">
                            {field.options.map((option, optionIndex) => (
                              <Choice
                                key={option + "-" + optionIndex}
                                active={chosen.includes(option)}
                                disabled={submitting}
                                kind={field.kind as "single" | "multiple"}
                                name={choiceName}
                                text={option}
                                onChange={() => chooseOption(index, field, option)}
                              />
                            ))}
                            <Choice
                              active={isCustom}
                              disabled={submitting}
                              kind={field.kind as "single" | "multiple"}
                              name={choiceName}
                              text="自己填写"
                              onChange={() => chooseCustom(index, field)}
                            />
                          </div>
                          {isCustom && (
                            <textarea
                              aria-label={field.label + "：自定义内容"}
                              aria-invalid={Boolean(errors[index])}
                              className="human-question-field__input"
                              placeholder="写下你的想法或补充说明"
                              value={customValues[index] ?? ""}
                              disabled={submitting}
                              onChange={(event) => { setCustomValues((previous) => ({ ...previous, [index]: event.target.value })); setErrors((previous) => ({ ...previous, [index]: "" })); }}
                            />
                          )}
                        </>
                      ) : (
                        <textarea
                          aria-label={field.label}
                          aria-invalid={Boolean(errors[index])}
                          className="human-question-field__input"
                          placeholder={field.placeholder || "在这里填写你的回答…"}
                          value={customValues[index] ?? ""}
                          disabled={submitting}
                          onChange={(event) => { setCustomValues((previous) => ({ ...previous, [index]: event.target.value })); setErrors((previous) => ({ ...previous, [index]: "" })); }}
                        />
                      )}
                      {errors[index] && <p id={formId + "-error-" + index} className="human-question-field__error" role="alert">{errors[index]}</p>}
                    </div>
                  </fieldset>
                );
              })}
            </div>

            <div className="human-question-card__footer">
              <p className="human-question-card__hint">可跳过选填项，也可在下方输入框直接回复</p>
              <button type="submit" disabled={submitting} className="human-question-card__submit">
                {submitting ? <Loader2 size={16} className="animate-spin" aria-hidden="true" /> : <Send size={16} aria-hidden="true" />}
                提交并继续
              </button>
            </div>
            {formError && <p className="human-question-card__form-error" role="alert">{formError}</p>}
          </form>
        )}
      </div>
    </section>
  );
}
