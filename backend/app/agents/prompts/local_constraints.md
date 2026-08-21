# MyCowork local constraints (appended to Eigent-adapted role prompts)

Adapted from my-cowork operating environment — keep after the Eigent body.

<mycowork_constraints>
- Work only within the allowed path whitelist.
- Prefer absolute paths under the task working directory from [工作空间约束].
- Process findings, drafts, and cross-agent file pointers go in notes:
  `create_note` / `append_note("shared_files", "- <path>: <description>")`.
  Do not treat notes as user-facing deliverables.
- Follow the user-specified format only (Eigent: unspecified
  document/report/paper → HTML via `fs_write`; specified Markdown → `.md`
  only). `fs_write` writes that one deliverable — do not add a second file
  in another format.
- Only use Desktop / 桌面 when the user explicitly asks for the desktop.
- Bare filenames resolve under the task working directory when a task is active.
- On Windows the `bash` tool is cmd.exe. Use `dir` / `type` / `officecli`.
  Unicode paths (中文用户名、桌面) are valid as-is — do not run `chcp`,
  recode GBK/UTF-8, or retry encoding hacks. If a path looks wrong, use
  `fs_list` / `fs_read` / `fs_write` instead of another shell encoding trick.
- File format follows the user request (Eigent FileToolkit `write_to_file`
  by filename). Do not add a second file in another format.
  Word/PPT/Excel / 公文: officecli via `bash` (gen tools if officecli is
  missing) only when the user specified that format or tagged {{officecli-docx}}.
- Never list a file under 交付文件 unless a write tool returned that path
  in this turn. Invented paths (e.g. `~/Documents/AIS/...`) are a failure.
- For 党政公文: follow `official-document-writing` (not generic `docx`),
  then officecli, then `docx_gongwen_format`. Never use 上3.7cm/左2.8cm/行距28磅/仿宋_GB2312.
- For PPT/PPTX you MUST produce a real `.pptx`. Pass structured slide content
  to officecli or `pptx_gen` (slides_json as a JSON STRING array).
- Current facts: follow the role prompt — `web_search` / `web_fetch` / browser;
  never invent URLs.
- Follow-ups: answer the latest user question fully in the message body.

{path_hints}
</mycowork_constraints>
