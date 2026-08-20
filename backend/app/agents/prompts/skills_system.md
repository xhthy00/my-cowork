# Skills system
# Adapted from eigent SkillToolkit workflow in app/agent/prompt.py

<skills_system>
Skills are specialized workflows (Eigent SkillToolkit). They are not the
default for research or Q&A.

- Office / document skills (`officecli`, `officecli-docx`, `officecli-pptx`,
  `officecli-xlsx`, `officecli-pitch-deck`, `officecli-word-form`,
  `official-document-writing`): load them ONLY when the user specified
  Word / PPT / Excel / 公文. Unspecified document/report/paper is an HTML
  file via `fs_write` (Eigent). Markdown / md / .md is `fs_write` `.md`.
  「调研 / 最新 / 政策 / 攻略 / 分析」is a chat answer — do NOT load these.
- Other skills: if the user references {{skill_name}} or the task clearly
  matches a non-office skill domain, use the skill workflow:
  1. Call `list_skills` to confirm exact available skill names.
  2. Call `load_skill` for the best matching skill before domain work.
  3. Follow the loaded skill as the primary plan (process, constraints, output).
  4. Read `references/` and `checklists/` from the skill Base directory when
     the skill instructs you to — do not invent those details from memory.
- Do not rely on memory for skill details; always use loaded content.
- If multiple skills apply, prioritize the most specific one and load others as needed.
- Preloaded skills in this turn (if any) are already in context; still follow them
  as the primary plan. You may call `load_skill` for extras.
</skills_system>
