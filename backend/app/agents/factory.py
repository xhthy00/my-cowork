"""Agent factory for workforce workers and single-agent ReAct agents."""

from pathlib import Path

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool

from app.agents.sanitize import ToolResponsesMiddleware
from app.agents.workers import WORKER_IDS

_PROMPTS_DIR = Path(__file__).parent / "prompts"

_WORKER_PROMPTS = {
    "developer_agent": "developer.md",
    "browser_agent": "browser.md",
    "document_agent": "document.md",
    "multi_modal_agent": "multi_modal.md",
    # legacy aliases
    "file_worker": "developer.md",
    "web_worker": "browser.md",
    "doc_worker": "document.md",
    "msg_worker": "multi_modal.md",
}


def _load_prompt(name: str) -> str:
    path = _PROMPTS_DIR / name
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def load_prompt(name: str, **placeholders: str) -> str:
    """Load ``prompts/<name>.md`` and substitute ``{key}`` placeholders.

    Uses literal replace (not str.format) so JSON braces in copied Eigent
    prompts stay intact.
    """
    filename = name if name.endswith(".md") else f"{name}.md"
    text = _load_prompt(filename)
    for key, value in placeholders.items():
        text = text.replace("{" + key + "}", str(value))
    return text


def load_worker_prompt(worker_name: str) -> str:
    """Load the system prompt for a named worker."""
    return _load_prompt(_WORKER_PROMPTS.get(worker_name, f"{worker_name}.md"))


def load_single_agent_prompt() -> str:
    """Load the Eigent-aligned Single Agent system prompt template."""
    return _load_prompt("single_agent.md")


def create_supervisor(model: BaseChatModel, tools: list[BaseTool] | None = None):
    """Deprecated no-op agent (workforce uses coordinator function node)."""
    return create_agent(
        model,
        tools or [],
        system_prompt="You are unused. Reply FINISH.",
        middleware=[ToolResponsesMiddleware()],
    )


def create_worker(
    name: str,
    system_prompt: str,
    model: BaseChatModel,
    tools: list[BaseTool] | None = None,
):
    """Create a named worker ReAct agent as a compiled graph."""
    _ = name
    return create_agent(
        model,
        tools or [],
        system_prompt=system_prompt,
        middleware=[ToolResponsesMiddleware()],
    )


def create_single_agent(
    system_prompt: str,
    model: BaseChatModel,
    tools: list[BaseTool] | None = None,
):
    """Create the Eigent-style Single Agent (full tool set, no routing)."""
    return create_agent(
        model,
        tools or [],
        system_prompt=system_prompt,
        middleware=[ToolResponsesMiddleware()],
    )


def known_worker_ids() -> tuple[str, ...]:
    return WORKER_IDS
