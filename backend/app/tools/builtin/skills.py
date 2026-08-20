"""Eigent-style SkillToolkit: list_skills / load_skill for agent invocation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.skills import find_skill, format_loaded_skill
from app.runtime.v2.office_gate import is_office_skill, office_skills_allowed
from app.skills.config import (
    default_skills_config_path,
    default_skills_root,
    list_skills_api,
    skill_visible_for_agent,
)


def _visible_skills(
    agent_id: str,
    *,
    root: Path | None,
    config_path: Path | None,
) -> list[dict[str, Any]]:
    skills = list_skills_api(root=root, config_path=config_path)
    if agent_id == "single_agent":
        rows = [s for s in skills if s.get("enabled", True)]
    else:
        rows = [s for s in skills if skill_visible_for_agent(s, agent_id)]
    if office_skills_allowed():
        return rows
    return [
        s
        for s in rows
        if not is_office_skill(str(s.get("id") or s.get("name") or ""))
    ]


def make_skill_tools(
    agent_id: str,
    *,
    root: Path | str | None = None,
    config_path: Path | str | None = None,
) -> list[StructuredTool]:
    """Create scoped ``list_skills`` / ``load_skill`` tools for one agent."""
    skills_root = Path(root) if root else default_skills_root()
    cfg_path = Path(config_path) if config_path else default_skills_config_path()

    def list_skills() -> str:
        """List skills available to the current agent."""
        rows = _visible_skills(agent_id, root=skills_root, config_path=cfg_path)
        payload = [
            {
                "name": s.get("id") or s.get("name"),
                "description": s.get("description") or "",
                "path": s.get("path"),
                "scope": s.get("scope"),
            }
            for s in rows
        ]
        return json.dumps(payload, ensure_ascii=False, indent=2)

    class _LoadArgs(BaseModel):
        name: str | list[str] = Field(
            description="A single skill name/id or list of names."
        )

    def load_skill(name: str | list[str]) -> str:
        """Load skill instructions into context and follow them as the plan."""
        names = name if isinstance(name, list) else [name]
        visible = _visible_skills(agent_id, root=skills_root, config_path=cfg_path)
        allowed = {str(s.get("id") or "") for s in visible} | {
            str(s.get("name") or "") for s in visible
        }
        chunks: list[str] = []
        for raw in names:
            key = str(raw or "").strip()
            if not key:
                continue
            if key not in allowed:
                chunks.append(
                    f"[ERROR] Skill {key!r} is not available to agent {agent_id!r}."
                )
                continue
            if is_office_skill(key) and not office_skills_allowed():
                chunks.append(
                    "[ERROR] The user asked for a chat answer, not a file. "
                    "Do not load officecli or document skills."
                )
                continue
            meta = find_skill(key, root=skills_root)
            if meta is None:
                chunks.append(f"[ERROR] Skill {key!r} not found on disk.")
                continue
            chunks.append(format_loaded_skill(meta))
        return "\n\n---\n\n".join(chunks) if chunks else "[ERROR] No skill name provided."

    load_description = (
        "Load one or more skills by name and return their full instructions. "
        "Call list_skills first when unsure of exact names. "
        "Follow the returned markdown as the primary plan. "
        "Do not load officecli / docx / pptx / xlsx skills unless the user "
        "specified Word / PPT / Excel / 公文."
    )

    return [
        StructuredTool.from_function(
            func=list_skills,
            name="list_skills",
            description=(
                "List skills available to you (name, description, path, scope). "
                "Call this before load_skill when the user references {{skill}} "
                "or a non-office skill domain. Office/document skills are omitted "
                "unless the user specified Word / PPT / Excel / 公文."
            ),
        ),
        StructuredTool.from_function(
            func=load_skill,
            name="load_skill",
            description=load_description,
            args_schema=_LoadArgs,
        ),
    ]
