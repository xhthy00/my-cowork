"""Eigent/CAMEL-style task analysis (post-subtask, not inside the Act loop)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from app.agents.factory import load_prompt
from app.runtime.context import last_ai_text, looks_like_plan_only, strip_think_blocks
from app.runtime.v2.office import validate_messages
from app.runtime.v2.synthesize import best_user_facing_text, current_turn_messages

_JSON_RE = re.compile(r"\{[\s\S]*\}")
QUALITY_THRESHOLD = 60
FAIL_OPEN_SCORE = 80
ANALYZE_MAX_RETRIES = 3
ENABLED_STRATEGIES = frozenset({"retry", "replan"})
RESEARCH_MARKERS = (
    "政策",
    "最新",
    "攻略",
    "价格",
    "新闻",
    "检索",
    "搜索",
    "调研",
    "对比",
)
_NOTE_WRITE = frozenset({"create_note", "append_note"})
_URL_RE = re.compile(r"https?://[^\s\]\"'<>）),，。；;]+")
_MIN_SEARCH_QUERIES = 2
_MIN_FETCHES = 2


def _is_fetch_tool(name: str) -> bool:
    n = (name or "").strip().lower()
    if not n or n in {"web_search", "web-search"}:
        return False
    if n in {"web_fetch", "web-fetch", "fetch"}:
        return True
    return "fetch" in n


@dataclass
class EvidenceInventory:
    search_queries: list[str] = field(default_factory=list)
    search_urls: set[str] = field(default_factory=set)
    fetch_urls: set[str] = field(default_factory=set)
    cited_urls: set[str] = field(default_factory=set)
    note_names: set[str] = field(default_factory=set)
    user_urls: set[str] = field(default_factory=set)
    findings_text: str = ""


def needs_research(user_text: str) -> bool:
    blob = user_text or ""
    return any(m in blob for m in RESEARCH_MARKERS)


def issues_need_search(issues: list[str] | None) -> bool:
    return any("web_search" in str(i) for i in (issues or []))


def issues_need_fetch(issues: list[str] | None) -> bool:
    return any("web_fetch" in str(i) for i in (issues or []))


def _norm_url(raw: str) -> str:
    return (raw or "").strip().rstrip(".,);]》'\"")


def _urls_in(text: str) -> set[str]:
    return {_norm_url(m) for m in _URL_RE.findall(text or "") if _norm_url(m)}


def _tool_calls(msg: Any) -> list[dict[str, Any]]:
    raw = list(getattr(msg, "tool_calls", None) or [])
    if not raw and isinstance(msg, dict):
        raw = list(msg.get("tool_calls") or [])
    out: list[dict[str, Any]] = []
    for call in raw:
        if isinstance(call, dict):
            args = call.get("args") or call.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {"input": args}
            out.append(
                {
                    "name": str(call.get("name") or ""),
                    "args": args if isinstance(args, dict) else {"input": args},
                }
            )
            continue
        args = getattr(call, "args", None) or {}
        out.append(
            {
                "name": str(getattr(call, "name", "") or ""),
                "args": args if isinstance(args, dict) else {"input": args},
            }
        )
    return [c for c in out if c.get("name")]


def _parse_search_urls(content: str) -> set[str]:
    found = _urls_in(content)
    try:
        rows = json.loads(content or "")
    except json.JSONDecodeError:
        return found
    if not isinstance(rows, list):
        return found
    for row in rows:
        if isinstance(row, dict):
            url = _norm_url(str(row.get("url") or ""))
            if url:
                found.add(url)
    return found


def collect_evidence(messages: list[Any], user_text: str = "") -> EvidenceInventory:
    """Pull search queries, result URLs, fetches, citations, and note names."""
    messages = current_turn_messages(messages)
    inv = EvidenceInventory(user_urls=_urls_in(user_text))
    queries: list[str] = []
    for msg in messages or []:
        name = str(getattr(msg, "name", "") or "")
        content = str(getattr(msg, "content", "") or "")
        role = str(getattr(msg, "type", None) or "")
        for call in _tool_calls(msg):
            cname = str(call.get("name") or "")
            args = call.get("args") or {}
            if cname == "web_search":
                q = str(args.get("query") or args.get("q") or "").strip()
                if q:
                    queries.append(q)
            elif _is_fetch_tool(cname):
                url = _norm_url(str(args.get("url") or ""))
                if url:
                    inv.fetch_urls.add(url)
            elif cname in _NOTE_WRITE:
                note = str(args.get("name") or "").strip()
                if note:
                    inv.note_names.add(note)
                if note.lower() == "findings":
                    inv.findings_text += str(args.get("content") or "")
        if name == "web_search":
            inv.search_urls |= _parse_search_urls(content)
        elif _is_fetch_tool(name):
            inv.fetch_urls |= _urls_in(content)
            if content.startswith("URL:"):
                first = content.split("\n", 1)[0][4:].strip()
                if first:
                    inv.fetch_urls.add(_norm_url(first))
        elif name in _NOTE_WRITE:
            low = content.lower()
            if "findings" in low:
                inv.note_names.add("findings")
            if "findings" in low and not content.lower().startswith("appended"):
                inv.findings_text += content
        if role in {"ai", "AIMessage", "assistant"}:
            inv.cited_urls |= _urls_in(content)
    seen: set[str] = set()
    unique: list[str] = []
    for q in queries:
        key = " ".join(q.split()).casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(q)
    inv.search_queries = unique
    return inv


def fetch_candidates(messages: list[Any], limit: int = 3) -> list[str]:
    """Search/user URLs not yet fetched, in first-seen order."""
    messages = current_turn_messages(messages)
    inv = collect_evidence(messages)
    ordered: list[str] = []
    seen: set[str] = set()
    for msg in messages or []:
        name = str(getattr(msg, "name", "") or "")
        content = str(getattr(msg, "content", "") or "")
        if name != "web_search":
            continue
        for url in _parse_search_urls(content):
            if url and url not in seen:
                seen.add(url)
                ordered.append(url)
    for url in inv.user_urls:
        if url not in seen:
            seen.add(url)
            ordered.append(url)
    return [u for u in ordered if u not in inv.fetch_urls][:limit]


def evidence_digest(messages: list[Any], limit: int = 2_000) -> str:
    """Compact URL/fetch list for workforce task.result."""
    inv = collect_evidence(messages)
    parts: list[str] = []
    if inv.search_queries:
        parts.append("queries: " + " | ".join(inv.search_queries[:6]))
    if inv.search_urls:
        parts.append("search: " + ", ".join(sorted(inv.search_urls)[:8]))
    if inv.fetch_urls:
        parts.append("fetched: " + ", ".join(sorted(inv.fetch_urls)[:8]))
    if inv.note_names:
        parts.append("notes: " + ", ".join(sorted(inv.note_names)))
    blob = "\n".join(parts)
    return blob if len(blob) <= limit else blob[:limit] + "…"


def evidence_floor_met(inv: EvidenceInventory) -> bool:
    """True when search+fetch already meet the research minimum (stop injecting)."""
    return (
        len(inv.search_queries) >= _MIN_SEARCH_QUERIES
        and len(inv.fetch_urls) >= _MIN_FETCHES
    )


@dataclass
class CriticVerdict:
    """Deterministic floor used by goldens (`next` is answer|act)."""

    covers_user_goal: bool = False
    needs_evidence: bool = False
    sources_ok: bool = True
    deliverable_ok: bool = True
    skill_followed: bool = True
    user_facing_complete: bool = False
    missing: list[str] = field(default_factory=list)
    next: str = "act"

    def as_dict(self) -> dict[str, Any]:
        return {
            "covers_user_goal": self.covers_user_goal,
            "needs_evidence": self.needs_evidence,
            "sources_ok": self.sources_ok,
            "deliverable_ok": self.deliverable_ok,
            "skill_followed": self.skill_followed,
            "user_facing_complete": self.user_facing_complete,
            "missing": list(self.missing),
            "next": self.next,
        }


@dataclass
class TaskAnalysisResult:
    quality_score: int = FAIL_OPEN_SCORE
    reasoning: str = ""
    issues: list[str] = field(default_factory=list)
    recovery_strategy: str | None = None
    modified_task_content: str | None = None

    def sufficient(self) -> bool:
        return self.quality_score >= QUALITY_THRESHOLD and self.recovery_strategy is None


def _tool_names(messages: list[Any]) -> set[str]:
    names: set[str] = set()
    for msg in messages:
        role = str(getattr(msg, "type", None) or "")
        name = str(getattr(msg, "name", "") or "")
        if role in {"tool", "ToolMessage"} or name:
            if name:
                names.add(name)
        for call in getattr(msg, "tool_calls", None) or []:
            if isinstance(call, dict) and call.get("name"):
                names.add(str(call["name"]))
    return names


def _wants_file(user_text: str) -> bool:
    from app.graphs.routing import wants_file_document

    return wants_file_document(user_text)


def _file_written(messages: list[Any], user_text: str = "") -> bool:
    from app.graphs.routing import (
        wants_document,
        wants_html_file,
        wants_markdown_file,
        wants_unspecified_document,
    )

    tools = _tool_names(messages)
    parts = [str(getattr(m, "content", "") or "") for m in messages]
    for m in messages:
        for call in _tool_calls(m):
            args = call.get("args") or {}
            if isinstance(args, dict):
                parts.append(str(args.get("path") or ""))
    blob = " ".join(parts).lower()
    fs_ok = bool(tools & {"fs.write", "fs_write"})
    office_ext = (".docx", ".pptx", ".xlsx", ".pdf", ".doc", ".ppt", ".xls")
    if wants_document(user_text):
        if "officecli" in blob and any(ext in blob for ext in office_ext):
            return True
        if tools & {"docx_gen", "pptx_gen", "xlsx_gen", "pdf_gen"}:
            return True
        return fs_ok and any(ext in blob for ext in office_ext)
    if wants_markdown_file(user_text):
        return fs_ok and ".md" in blob
    if wants_html_file(user_text) or wants_unspecified_document(user_text):
        return fs_ok and (".html" in blob or ".htm" in blob)
    return False


def evidence_gate(
    user_text: str,
    messages: list[Any],
    *,
    apply_research: bool | None = None,
    require_findings: bool = False,
) -> CriticVerdict:
    """Deterministic evidence bar: search diversity + fetch + citations."""
    return heuristic_critic(
        user_text,
        messages,
        apply_research=apply_research,
        require_findings=require_findings,
    )


def heuristic_critic(
    user_text: str,
    messages: list[Any],
    *,
    apply_research: bool | None = None,
    require_findings: bool = False,
    skip_file_gate: bool = False,
) -> CriticVerdict:
    """Deterministic completeness floor (goldens + analyze_task gate)."""
    messages = current_turn_messages(messages)
    ai = best_user_facing_text(messages) or last_ai_text(messages)
    body = strip_think_blocks(ai)
    need_doc = False if skip_file_gate else _wants_file(user_text)
    doc_ok = _file_written(messages, user_text) if need_doc else True
    plan_only = looks_like_plan_only(user_text, ai)
    research = needs_research(user_text) if apply_research is None else bool(apply_research)
    inv = collect_evidence(messages, user_text)
    user_q = " ".join((user_text or "").split()).casefold()
    distinct = inv.search_queries
    not_verbatim = [
        q
        for q in distinct
        if " ".join(q.split()).casefold() != user_q
    ]
    allowed_fetch = inv.search_urls | inv.user_urls
    valid_fetches = {
        u
        for u in inv.fetch_urls
        if (not allowed_fetch) or u in allowed_fetch or any(
            u.startswith(s) or s.startswith(u) for s in allowed_fetch
        )
    }
    cited_ok = bool(inv.cited_urls & valid_fetches) or bool(
        inv.cited_urls & inv.fetch_urls
    )
    missing: list[str] = []
    if plan_only:
        missing.append("Write the complete user-facing answer, not a plan.")
    if need_doc and not doc_ok:
        from app.graphs.routing import wants_document, wants_markdown_file

        if wants_markdown_file(user_text) and not wants_document(user_text):
            missing.append("Write a .md file with fs_write.")
        elif wants_document(user_text):
            missing.append("Write a real office file with officecli or a gen tool.")
        else:
            missing.append("Write an HTML file with fs_write.")
    if not body.strip():
        missing.append("Produce a non-empty user-facing reply.")
    sources_ok = True
    if research:
        if len(distinct) < _MIN_SEARCH_QUERIES or not not_verbatim:
            missing.append(
                "Call web_search with at least 2 distinct queries "
                "(not only the user sentence)."
            )
            sources_ok = False
        if len(inv.fetch_urls) < _MIN_FETCHES:
            missing.append(
                "Call web_fetch on at least 2 URLs from search results "
                "(or URLs the user provided)."
            )
            sources_ok = False
        elif body.strip() and not cited_ok:
            missing.append("Cite at least one fetched URL in the user-facing answer.")
            sources_ok = False
        if require_findings:
            names = {n.lower() for n in inv.note_names}
            if "findings" not in names:
                missing.append(
                    "Record findings in a shared note via create_note/append_note "
                    "with name=findings."
                )
            elif not (_urls_in(inv.findings_text) or len(inv.findings_text.strip()) >= 40):
                missing.append(
                    "findings note must quote facts with a source URL "
                    "or a substantial excerpt."
                )
    ok_files, file_issues = validate_messages(messages)
    if not ok_files:
        missing.extend(file_issues)
        doc_ok = False
    ok = not missing
    return CriticVerdict(
        covers_user_goal=ok and not plan_only,
        needs_evidence=research and not sources_ok,
        sources_ok=sources_ok if research else True,
        deliverable_ok=doc_ok,
        skill_followed=True,
        user_facing_complete=bool(body) and not plan_only,
        missing=missing,
        next="answer" if ok else "act",
    )


def _messages_for(user_text: str, result: str, messages: list[Any] | None) -> list[Any]:
    if messages:
        return messages
    return [
        HumanMessage(content=user_text or ""),
        AIMessage(content=result or ""),
    ]


def floor_analysis(
    user_text: str,
    messages: list[Any],
    *,
    apply_research: bool | None = None,
    require_findings: bool = False,
    skip_file_gate: bool = False,
) -> TaskAnalysisResult | None:
    """Return an insufficient result when the deterministic floor fails."""
    verdict = heuristic_critic(
        user_text,
        messages,
        apply_research=apply_research,
        require_findings=require_findings,
        skip_file_gate=skip_file_gate,
    )
    if verdict.next == "answer":
        return None
    return TaskAnalysisResult(
        quality_score=0,
        reasoning="Deterministic completeness floor failed.",
        issues=list(verdict.missing),
        recovery_strategy="retry",
    )


def _parse_analysis(raw: str) -> TaskAnalysisResult | None:
    m = _JSON_RE.search(raw or "")
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    try:
        score = int(data.get("quality_score") if data.get("quality_score") is not None else 0)
    except (TypeError, ValueError):
        score = 0
    score = max(0, min(100, score))
    issues = data.get("issues") or []
    if not isinstance(issues, list):
        issues = [str(issues)]
    strategy = data.get("recovery_strategy")
    if strategy is not None:
        strategy = str(strategy).strip().lower() or None
        if strategy in {"none", "null"}:
            strategy = None
        elif strategy not in ENABLED_STRATEGIES:
            strategy = "retry" if score < QUALITY_THRESHOLD else None
    modified = data.get("modified_task_content")
    modified_s = str(modified).strip() if modified else None
    if score >= QUALITY_THRESHOLD:
        strategy = None
    elif strategy is None:
        strategy = "retry"
    if strategy != "replan":
        modified_s = None
    return TaskAnalysisResult(
        quality_score=score,
        reasoning=str(data.get("reasoning") or ""),
        issues=[str(x) for x in issues],
        recovery_strategy=strategy,
        modified_task_content=modified_s or None,
    )


async def _invoke_analysis_llm(llm: Any, prompt: str) -> str | None:
    if llm is None:
        return None
    try:
        if hasattr(llm, "ainvoke"):
            msg = await llm.ainvoke(
                [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "Return the JSON analysis now."},
                ]
            )
            return str(getattr(msg, "content", None) or msg)
    except Exception:
        return None
    return None


async def analyze_task(
    task_content: str,
    result: str,
    *,
    for_failure: bool = False,
    error_message: str | None = None,
    llm: Any | None = None,
    failure_count: int = 0,
    messages: list[Any] | None = None,
    user_text: str = "",
    task_id: str = "",
    assigned_worker: str = "",
) -> TaskAnalysisResult:
    """Post-subtask quality analysis (Eigent `_analyze_task`)."""
    blob = (user_text or task_content or "").strip()
    result_text = (result or error_message or "").strip()
    if not result_text or result_text.upper().startswith("FAILED"):
        return TaskAnalysisResult(
            quality_score=0,
            reasoning="Empty or FAILED worker result.",
            issues=[error_message or "Produce a non-empty user-facing reply."],
            recovery_strategy="retry",
        )
    msgs = _messages_for(blob, result_text, messages)
    gate_text = (task_content or blob).strip() or blob
    if assigned_worker and task_content:
        gate_text = task_content
    apply_research: bool | None = None
    require_findings = False
    if assigned_worker:
        apply_research = assigned_worker == "browser_agent" and needs_research(
            f"{user_text} {task_content}"
        )
        require_findings = apply_research
    floor = floor_analysis(
        gate_text or blob,
        msgs,
        apply_research=apply_research,
        require_findings=require_findings,
        skip_file_gate=assigned_worker == "browser_agent",
    )
    if floor is not None:
        return floor
    research = assigned_worker == "browser_agent" or needs_research(gate_text or blob)
    if research:
        # Floor already passed. Another critic LLM used to send the same
        # research worker back for 40 more search steps (20+ minute runs).
        return TaskAnalysisResult(
            quality_score=FAIL_OPEN_SCORE,
            reasoning="Research completeness floor passed.",
            recovery_strategy=None,
        )

    issue_type = "failure" if for_failure else "quality"
    extra = (
        f"The worker reported failure: {error_message or result_text}"
        if for_failure
        else "Evaluate completeness, accuracy, and missing deliverables."
    )
    prompt = load_prompt(
        "critic",
        issue_type=issue_type,
        task_id=task_id or "(none)",
        task_content=task_content or blob,
        task_result=result_text or "(empty)",
        failure_count=str(failure_count),
        assigned_worker=assigned_worker or "(none)",
        issue_specific_analysis=extra,
    )
    parsed: TaskAnalysisResult | None = None
    for _ in range(ANALYZE_MAX_RETRIES):
        raw = await _invoke_analysis_llm(llm, prompt)
        if not raw:
            continue
        parsed = _parse_analysis(raw)
        if parsed is not None:
            break
    if parsed is None:
        if for_failure:
            return TaskAnalysisResult(
                quality_score=0,
                reasoning="Failure analysis exhausted retries; halt this subtask.",
                issues=[error_message or "worker failed"],
                recovery_strategy=None,
            )
        if needs_research(gate_text or blob):
            return TaskAnalysisResult(
                quality_score=0,
                reasoning="Quality analysis failed; research tasks cannot fail-open.",
                issues=["Re-run research with web_search and web_fetch."],
                recovery_strategy="retry",
            )
        return TaskAnalysisResult(
            quality_score=FAIL_OPEN_SCORE,
            reasoning="Quality analysis failed; accepting the task result.",
            recovery_strategy=None,
        )
    return parsed


def finalize_worker_result(
    *,
    task: dict[str, Any],
    summary: str,
    analysis: TaskAnalysisResult,
    max_retries: int = 3,
) -> dict[str, Any]:
    """Map analysis onto a subtask patch (status / retries / content)."""
    retries = int(task.get("retries") or 0)
    content = str(task.get("content") or "")
    strategy = analysis.recovery_strategy
    if strategy in ENABLED_STRATEGIES and retries < max_retries:
        new_content = content
        if strategy == "replan" and analysis.modified_task_content:
            new_content = analysis.modified_task_content
        return {
            "id": str(task.get("id") or ""),
            "status": "waiting",
            "result": "",
            "retries": retries + 1,
            "content": new_content,
            "quality_score": analysis.quality_score,
        }
    status = "completed" if analysis.sufficient() else "failed"
    return {
        "id": str(task.get("id") or ""),
        "status": status,
        "result": (summary or "")[:4000],
        "retries": retries,
        "quality_score": analysis.quality_score,
    }
