---
name: officecli-financial-model
description: "Use this skill for financial models, scenarios, and projections — Assumptions, P&L, cash flow, unit economics, three-statement sketches. Trigger on: 财务模型, financial model, projections, 情景分析, P&L, cash flow model, unit economics workbook. Output is .xlsx. Scene layer on officecli-xlsx. DO NOT use for generic trackers or KPI-only dashboards (route those to officecli-xlsx or officecli-data-dashboard)."
---

# OfficeCLI Financial Model Skill

**Scene layer on `officecli-xlsx`.** Inherit xlsx formula/chart/validate rules. This file adds **model discipline**: Assumptions sheet, linked statements, scenario toggles, number contracts, and a Delivery Gate.

When unsure about a prop, run `officecli help xlsx <element>` — help wins.

## When to use / hand off

| Use this skill | Hand off |
|---|---|
| Multi-year P&L / cash / simple BS driven by drivers | Flat sales tracker → `officecli-xlsx` |
| Unit economics (CAC, LTV, payback) with assumptions | KPI executive board without model → `officecli-data-dashboard` |
| Seed / Series planning workbooks | Investor pitch narrative slides → `officecli-pitch-deck` |

## Setup

Same as `officecli` / `officecli-xlsx`. Verify with `officecli --version`.

## Model architecture (default)

| Sheet | Role |
|---|---|
| `Assumptions` | All drivers: price, growth, headcount, churn, tax, starting cash. **No hard-coded drivers on other sheets.** |
| `P&L` (or `IS`) | Revenue → COGS → Gross profit → OpEx → EBITDA / Net income by period |
| `Cash` | Starting cash, burn / collections, ending cash, runway |
| `UnitEcon` (optional) | CAC, LTV, payback, contribution margin |
| `Scenarios` (optional) | Base / Upside / Downside switches or side-by-side columns |

Periods: monthly for ≤18 months, or quarterly/yearly for 3-year views. Label periods in a header row (`2026-Q1` …).

## Rules of good models

1. **Single source of truth** — every driver lives on Assumptions; other sheets only reference it.
2. **No magic numbers** in P&L/Cash — if you need a constant, put it on Assumptions and name it.
3. **Signs & units** — revenue positive; costs as positive outflows with clear labels, or negative with a legend — pick one convention and stick to it.
4. **Scenarios** — prefer a `Scenario` cell (`Base`/`Upside`/`Downside`) with `INDEX/MATCH` or parallel columns; document which is active.
5. **Checks** — add a `Checks` area: balance identities, cash non-negative flag, growth sanity.
6. **Charts** — optional revenue / cash trajectory; y-axis starts at 0.

## Minimal SaaS skeleton (example drivers)

Assumptions examples: Starting ARR, MoM growth, Gross margin %, Sales & Marketing, R&D, G&A, CAC, logo churn, starting cash.

P&L examples: ARR/Revenue, COGS, Gross profit, OpEx lines, Operating income.

Cash examples: Beginning cash, Net change, Ending cash, Runway (months).

Adapt to the user's business (commerce, services, hardware) — do not force SaaS labels when inappropriate.

## Shell note

Single-quote formula or text containing `$` in shell commands so the shell does not expand `$ARR`-like tokens.

## Delivery Gate

1. **Sheets** — at least `Assumptions` + one statement sheet (`P&L` or `Cash`).
2. **Links** — statement cells reference Assumptions (spot-check ≥3 formulas); no duplicate driver hard-codes.
3. **Periods** — ≥4 periods labeled; totals or ending cash visible.
4. **Integrity** — no `#REF!` / `#DIV/0!`; Checks area notes any intentional simplifications.
5. **Story** — one short comment or title stating scenario horizon (e.g. 「三年 Base 情景」).
6. **Validate** — workbook opens; `officecli validate` clean when available.

Fresh-eyes: can a CFO change one Assumption and see P&L/Cash move without editing other sheets?
