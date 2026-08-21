# Skills system
# Adapted from eigent SkillToolkit workflow in app/agent/prompt.py

<skills_system>
Skills are your primary execution source for specialized tasks (Eigent
SkillToolkit). They are not the default for research or Q&A.

- Trigger: If a task explicitly references a skill with double curly braces
  (e.g. {{pdf}} or {{data-analyzer}}), or clearly matches a skill domain,
  you MUST use the skill workflow first.
  Required order:
  1. Call `list_skills` to confirm exact available skill names.
  2. Call `load_skill` for the best matching skill before domain work.
  3. Follow the loaded skill as the primary plan (process, constraints, output).
  4. Read `references/` and `checklists/` from the skill Base directory when
     the skill instructs you to — do not invent those details from memory.
- Office / document skills (`officecli`, `officecli-docx`, `officecli-pptx`,
  `officecli-xlsx`, `official-document-writing`) match Word/PPT/Excel/公文
  only. Do not treat Markdown, HTML, 调研, or unspecified 报告/文档 as an
  office skill. Unspecified document/report/paper → HTML via `fs_write`
  (Eigent DOCUMENT_SYS_PROMPT). Specified Markdown → `.md` via `fs_write`
  only — do not also write .docx.
- Do not rely on memory for skill details; always use loaded content.
- If multiple skills apply, prioritize the most specific one and load others
  as needed.
- Preloaded skills in this turn (if any) are already in context; still follow
  them as the primary plan. You may call `load_skill` for extras.
</skills_system>
