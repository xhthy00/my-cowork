---
name: officecli-word-form
description: "Use this skill when the document's purpose is data capture — fillable intake forms, contracts/SOWs with user-fill slots, HR onboarding, questionnaires, compliance checklists, mail-merge-ready templates. Trigger on: 表单, fillable form, content control, 合同填空, NDA template slots, intake form. Output is .docx. Scene layer on officecli-docx. DO NOT use for plain reports, letters, memos, or proposals without fill slots (route those to officecli-docx)."
---

# OfficeCLI Word Form Skill

**Scene layer on `officecli-docx`.** Inherit docx layout, styles, and validate rules. This file adds **data-capture** structure: labeled fields, content controls / clear fill slots, protection notes, and a Delivery Gate.

When unsure about a control or prop, run `officecli help docx <element>` — help wins.

## When to use / hand off

| Use this skill | Hand off |
|---|---|
| Intake / HR / medical / compliance forms | Narrative reports → `officecli-docx` |
| Contracts with blank party/date/amount slots | Academic papers → academic skill (not this) |
| Checklists meant to be filled digitally or printed | Pure slide decks → pptx skills |

## Setup

Same as `officecli` / `officecli-docx`. Verify with `officecli --version`.

## Design principles

1. **One purpose per form** — title states what is being collected and for whom.
2. **Label left / field right** (or label above field on narrow layouts). Never rely on underlined blanks alone without a label.
3. **Field types** — prefer structured slots:
   - Short text: name, phone, email, ID
   - Long text: remarks / description
   - Date / number / currency where applicable
   - Yes/No or single-choice for binary decisions
   - Signature + date block at the end for agreements
4. **If content controls are available** via officecli, use them (`sdt` / form fields). If the installed CLI cannot emit SDT, create a **clear print-fill template**: `[________________]` or `【填写】` placeholders with consistent width, and tell the user it is print/fill style.
5. **Instructions** — 2–4 lines at the top: who fills, required vs optional, submit target.
6. **Privacy** — do not invent sensitive sample PII; use obvious placeholders (`张三`, `138****0000`).

## Structure template

```
Title
Instructions (short)
Section 1 — Basic info (table or definition list of fields)
Section 2 — Details / checklist
Section 3 — Declaration / signature / date
Footer — version / owner
```

For **contracts with slots**: keep legal body readable; mark slots as `【甲方名称】` / `【签署日期】` consistently; group all fill slots in an appendix table if the body would become unreadable.

## Delivery Gate

1. **Identity** — title + instructions present; purpose is data capture, not a prose report.
2. **Fields** — ≥5 labeled fill slots (or content controls); every blank has a label.
3. **Consistency** — placeholder style is uniform; required fields marked（* 或「必填」）.
4. **Signature** — agreements include signatory + date lines when relevant.
5. **Validate** — docx opens; no broken tables; `officecli validate` clean when available.

Fresh-eyes: can someone fill this without asking what each blank means?
