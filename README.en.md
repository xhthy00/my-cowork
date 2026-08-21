<p align="center">

<img src="./docs/screenshots/app-icon.png" width="96" alt="MyCowork" />

</p>

<h1 align="center">MyCowork</h1>

<p align="center">
  <strong>A local office coworker</strong> · Chat to deliver Word, Excel, PPT, and official documents<br />
  Fat desktop client · Local-first · Bring your own keys · Single-agent / multi-agent
</p>

<p align="center">
  Electron · React · FastAPI · LangGraph · OfficeCLI
</p>

<p align="center">
  <a href="./README.md">中文</a> · <strong>English</strong>
</p>

MyCowork is an office agent that runs on your own computer. Describe a task; the assistant reads and writes your local workspace, produces files you can open, and previews them in the same window. It sits in the same category as Claude Cowork / WorkBuddy-style “digital employees”, but models, files, and API keys stay on-device. Each teammate installs independently; nothing is shared by default.

---

## Screenshots

Single-agent home: one cow coworker, best when you just want to get one thing done.

![Single-agent home](./docs/screenshots/home-single-agent.png)

Multi-agent home: a whole cow team, better for decomposition, parallelism, and mixed-format delivery.

![Multi-agent home](./docs/screenshots/home-multi-agent.png)

Workspace: chat, task list, deliverable cards, and a live document preview on one screen.

![Workspace chat and document preview](./docs/screenshots/workspace.png)

---

## What it does

- **Writes to disk locally**: Outputs land in your workspace (default like `~/Documents/AIS`), not a cloud draft. Process notes stay out of the sidebar; nothing outside the workspace is touched.
- **Two execution modes**
  - **Single agent**: one ReAct agent runs the whole job — lightweight, good for a single document or Q&A.
  - **Multi-agent (Workforce)**: a planner splits the work → you confirm subtasks → a coordinator fans out document / browser / developer workers by dependency, and can replan on failure.
- **Office assistant catalog**: scene-specific skills are preloaded so you can start weekly reports, official documents, forms, dashboards, financial models, or contract review in one click.
- **Skills + SkillHub**: toggle local skills, grant them to specific agents, or browse and install suites from SkillHub.
- **Built-in model panel**: Anthropic, OpenAI, OpenRouter, DeepSeek, Tongyi, Moonshot, MiniMax, plus local Ollama, LM Studio, and vLLM. Keys live in the OS keychain and are saved only after a successful validate.
- **Connectors and browser**: MCP for everyday tools; Playwright MCP for browser automation (Chromium is installed on demand).
- **Memory, timers, scheduling**: long-term memory in local SQLite; skills with a `schedule` are registered with on-device APScheduler (the app must stay running).
- **Optional remote entry**: a Lark/Feishu bot can expose local `/webhook/lark` over HTTPS via Cloudflare Tunnel (unreachable when the machine is off).

### Office assistants

![Document assistants](./docs/screenshots/assistants-docs.png)

| Category | Assistants | Typical output |
| --- | --- | --- |
| Presentations | PPT assistant, pitch-deck assistant | `.pptx` reviews / fundraising decks |
| Documents | Word assistant, official-document writer, Word form assistant | Weekly reports, requests/notices, fillable forms |
| Spreadsheets | Excel assistant, data-dashboard assistant, financial-model assistant | Ledgers, KPI boards, three-statement models |
| Legal | China legal counsel | Contract review / drafting (mainland-China knowledge base) |
| General | Office collaboration assistant | Switch among PPT / Word / Excel in one task |

Official-document writing follows common agency manuscript layout (title and body fonts, line spacing, and so on). Red-header issuance follows GB/T 9704-2012. Legal and official-document modes are **drafting / QA aids only** — not formal issuance or legal advice.

![Spreadsheet assistants](./docs/screenshots/assistants-tables.png)

![Legal and general office assistants](./docs/screenshots/assistants-legal.png)

Document generation prefers the bundled [OfficeCLI](https://github.com/iOfficeAI/OfficeCLI) binary (`officecli`). Local preview uses OfficeCLI watch as well; if it is unavailable, the app falls back to built-in `docx_gen` / `xlsx_gen` / `pptx_gen` and a simpler preview.

### Skills and models

Local skills can be toggled. SkillHub recommends suites by office productivity, content, engineering, data, design, knowledge management, and more.

![Skills and SkillHub](./docs/screenshots/skills.png)

The models page supports cloud vendors and local inference. OpenRouter, Ollama, and similar providers are normalized to the OpenAI-compatible protocol when injected into the backend.

![Model configuration](./docs/screenshots/models.png)

---

## Architecture

Fat desktop client: Electron starts a local Python (FastAPI) process. The renderer talks over localhost HTTP + SSE for chat and traces. Tool calls run in-process on the machine — there is no remote-to-local WebSocket callback.

```
┌────────────────────────── This machine ──────────────────────┐
│  Electron renderer (React)                                   │
│   Chat / workspace / assistants / skills / models / confirms │
│                         │ HTTP + SSE                         │
│  Electron main (Node)                                        │
│   Spawn backend · keychain · PDF printToPDF · file dialogs   │
│                         │ localhost                          │
│  Python (FastAPI + LangGraph)                                │
│   Orchestrate → graph (single / workforce) → tools / MCP     │
│   SQLite + sqlite-vec · APScheduler · Lark webhook           │
└──────────────────────────────────────────────────────────────┘
         Optional: Cloudflare Tunnel → Lark event subscription
```

The backend is split into nine harness layers. Dependencies may only point downward (`import-linter` enforces this in CI):

| Layer | Package | Role |
| --- | --- | --- |
| L9 Ingress | `backend/app/server/` | HTTP / SSE / webhooks / scheduled triggers |
| L8 Orchestration | `orchestrator/` | Task lifecycle, sessions |
| L7 Runtime | `graphs/` `agents/` `runtime/` | LangGraph, checkpoints, token budget |
| L6 Memory | `memory/` | Short-term context + long-term vectors |
| L5 Observability | `observability/` | Traces, redacted logs, usage |
| L4 Guardrails | `guardrails/` | Approval gates, dangerous-command deny, audit |
| L3 Tools | `tools/` | fs / exec / documents / MCP / skills |
| L2 Models | `llm/` | Provider gateway, token counting |
| L1 Sandbox | `sandbox/` | Path allowlist, egress policy |

Keys are not written to `config.toml`. Electron stores them in the OS keychain (macOS Keychain / Windows Credential Manager) and injects them as env vars when starting Python.

---

## Tech stack

| Area | Choice |
| --- | --- |
| Desktop shell | Electron 35, electron-builder (dmg / NSIS) |
| UI | React 19, Vite, TypeScript, Tailwind, Radix, Zustand |
| Backend | Python 3.11, FastAPI, Uvicorn, uv |
| Agent | LangGraph supervisor / workforce, LangChain model adapters |
| Office files | OfficeCLI + python-docx / python-pptx / openpyxl |
| Data | SQLite, sqlite-vec |
| Remote | lark-oapi, Cloudflare Tunnel (optional) |

---

## Quick start

### Requirements

- Node.js 20+
- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- macOS or Windows

### Development

```bash
cd backend && uv sync
cd .. && npm install

# High-fidelity office generation / preview
npm run fetch:officecli

npm run dev
```

`npm run dev` starts Vite (`127.0.0.1:5174`), TypeScript watch, and Electron together.

You can also run them separately:

```bash
npm run dev:renderer
cd backend && uv run uvicorn app.main:app --port 8765
npm run dev:electron
```

First launch: open **Agents → Models**, pick a vendor, fill in the API key and model ID, then save (writes only after validation). Chat once the title bar shows the backend is connected.

Smoke test:

> Write hello.txt on the Desktop with contents hi

After you allow the write confirmation, the file should appear on the Desktop.

### Tests

```bash
cd backend && PYTHONPATH=. uv run pytest -q
cd backend && PYTHONPATH=. uv run lint-imports
npm test
npm run test:e2e    # requires npm run build first
```

### Installers

Release artifacts come from GitHub Actions (`.github/workflows/build.yml`):

- macOS: `MyCowork-*.dmg`
- Windows: `MyCowork Setup *.exe` (NSIS; SmartScreen may warn if unsigned)

Build locally:

```bash
npm run build:python:mac      # or npm run build:python:windows on Windows
bash scripts/build-electron.sh --mac
# Windows: npx electron-builder --config build/electron-builder.yml --win
```

If macOS Gatekeeper blocks the app: System Settings → Privacy & Security → Open Anyway, or:

```bash
xattr -dr com.apple.quarantine /Applications/MyCowork.app
```

Full install and Lark remote steps: [docs/部署手册.md](docs/部署手册.md) (Chinese).

---

## Usage

1. **Workspace**: pick a project/session on the left; chat in the middle; preview delivered `.docx` / `.pptx` / `.xlsx` on the right.
2. **Agents**
   - Models: configure cloud or local LLMs; one can be the default.
   - Skills: toggle local skills, grant them to agents, or install from SkillHub.
   - Office assistants: start from a scene; matching skills are preloaded and a suggested prompt is filled into the composer.
   - Memory: togglable. Saying “remember …” writes to `~/.my-cowork/memory.db`.
3. **Connectors**: MCP servers. You can also edit `~/.my-cowork/mcp.json`, or copy `config.template.toml` to `config.toml`.
4. **Confirmations**: writes, shell commands, and document generation pop a gate. Check the path before allowing. Later `officecli` calls in the same task may be auto-approved.
5. **Schedules**: add `schedule` in a skill’s `skill.yaml` to register; the client must stay running.

Skill conventions: [docs/开发指南.md](docs/开发指南.md) (Chinese) and [skills/README.md](skills/README.md).

---

## Safety

- **Local-first, single-tenant**: no cloud hosting, multi-tenancy, billing, or SSO.
- **Path allowlist**: includes the home directory by default; tighten it in settings. `../` escape is rejected.
- **Dangerous commands denied**: e.g. destructive `rm -rf /` against the filesystem root.
- **Remote channel is tighter**: skills that write disk, `exec`, or generate documents cannot be triggered via Lark; webhooks need a verify token and source IPs.
- **Out of scope**: desktop GUI Computer Use, training your own models, 24/7 unattended operation (timers and webhooks stop when the app is quit).

---

## Repository layout

```
backend/                 Python backend (harness layers)
electron/                Electron main process
renderer/                React UI
skills/                  User / workspace skills
resources/example-skills Bundled skills (official docs, legal, officecli recipes, …)
resources/bin/           Platform binaries from fetch:officecli (not committed)
build/                   electron-builder config and app icon
scripts/                 Dev, packaging, dependency fetch
docs/                    Dev/deploy docs and README screenshots
```

Design notes: [落地方案.md](落地方案.md) · task plan: [开发计划.md](开发计划.md) (both Chinese).

---

## Further docs

- [开发指南](docs/开发指南.md) — local development, tests, skills / MCP / office assistants (Chinese)
- [部署手册](docs/部署手册.md) — install, first-run setup, Lark tunnel, safety notes (Chinese)

---

## License

This repository is released under the [MIT License](LICENSE). Third-party skills bundled under `resources/example-skills/` keep the original license in each skill directory.
