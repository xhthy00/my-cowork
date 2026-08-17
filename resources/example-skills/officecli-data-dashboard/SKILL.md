---
name: officecli-data-dashboard
description: "Use this skill when the user wants a KPI / analytics / executive dashboard from CSV or tabular data — charts, sparklines, filterable summary sheets. Trigger on: dashboard, KPI board, 经营看板, 数据仪表盘, executive summary workbook. Output is .xlsx. Scene layer on officecli-xlsx. DO NOT use for raw trackers, ledgers, or financial three-statement models (route those to officecli-xlsx or officecli-financial-model)."
---

# OfficeCLI Data Dashboard Skill

**Scene layer on `officecli-xlsx`.** Inherit every xlsx hard rule (formulas, charts, formatting, validate). This file adds only what a **dashboard** needs: KPI layout, chart choice, filter/slicer discipline, and a Delivery Gate.

When unsure about a prop or chart type, run `officecli help xlsx <element>` — help wins.

## When to use / hand off

| Use this skill | Hand off |
|---|---|
| KPI cards + trend/breakdown charts from tabular data | Raw data entry / tracker → `officecli-xlsx` |
| Executive one-pager workbook (Dashboard sheet + Data sheet) | Three-statement / scenario model → `officecli-financial-model` |
| Region / product performance board with filters | Fundraising deck charts → `officecli-pitch-deck` |

## Setup

Same as `officecli` / `officecli-xlsx`. Verify with `officecli --version`.

## Workflow

1. **Clarify metrics** — pick 4–8 KPIs (e.g. Revenue, MoM%, Orders, AOV, Conversion, Active users). Ask only if the source columns are ambiguous.
2. **Sheet map**
   - `Data` — cleaned source table (one header row, typed columns).
   - `Dashboard` — KPI row + 2–4 charts + optional detail table. Never put chart-only chaos on Data.
   - Optional `Lookup` — dimension maps / targets.
3. **KPI row** — large labels + values (formulas referencing Data). Include period label (e.g. `2026-W31` or `2026-07`).
4. **Charts** — choose by intent:
   - Trend over time → line / area
   - Rank / compare categories → bar
   - Mix / share → pie only if ≤6 slices
   - Target vs actual → combo or dual series
5. **Filters** — freeze header on Data; use AutoFilter. If the user asked for interactive slicing, document which columns to filter.
6. **Style** — one accent color; consistent number formats (`#,##0`, `0.0%`); chart titles in Chinese or English matching the user.

## Minimal structure template

```
Dashboard!
  A1:title   B1:period
  A3:KPI1_label  B3:KPI1_value
  A4:KPI2_label  B4:KPI2_value
  ...
  charts below KPI block
Data!
  header row + records
```

## Delivery Gate

Before handing off, check:

1. **Sheets** — `Dashboard` + `Data` both exist; Dashboard has no raw paste dump longer than ~20 rows without summary.
2. **KPIs** — ≥4 KPI values are formulas (not hard-coded), and period is visible.
3. **Charts** — ≥2 charts with titles; axes start at 0 for bar/line unless a log scale was requested.
4. **Numbers** — currency / percent formats correct; no `#REF!` / `#DIV/0!`.
5. **Validate** — `officecli validate` (or equivalent) clean, or known warnings explained to the user.

Fresh-eyes: would a manager understand the board in 10 seconds without reading the Data sheet?
