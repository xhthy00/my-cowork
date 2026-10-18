"""Versioned JSON contract; contains no agent-framework or product imports."""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PROTOCOL_VERSION = 1


def _form_items(value):
    # Some XML-oriented tool serializers wrap arrays (including singletons).
    while isinstance(value, dict) and set(value) == {'item'}:
        value = value['item']
    return value


def _form_options(value):
    value = _form_items(value)
    if isinstance(value, dict) and 'label' in value:
        value = [value]
    if isinstance(value, list):
        return [item['label'] if isinstance(item, dict) and 'label' in item else item for item in value]
    return value


class HumanQuestionField(BaseModel):
    """Form input shared by the host and independent harness."""
    label: str = Field(description="A short question or field label in the user's language")
    kind: Literal['single', 'multiple', 'text'] = Field(description="Single choice, multiple choice, or free text")
    options: list[str] = Field(default_factory=list, description="Short choices for single/multiple fields; the UI also permits a custom answer")
    required: bool = Field(default=False, description="True only when this answer is necessary to continue")
    placeholder: str = Field(default='', description="Brief example for a text answer")

    @model_validator(mode='before')
    @classmethod
    def normalize_question_label(cls, value):
        if isinstance(value, dict) and 'label' not in value and 'question' in value:
            return {**value, 'label': value['question']}
        return value

    @field_validator('options', mode='before')
    @classmethod
    def normalize_options(cls, value):
        return _form_options(value)


class HumanQuestionInput(BaseModel):
    question: str = Field(description="Brief introduction explaining what the user needs to clarify")
    options: list[str] | None = Field(default=None, description="Suggested choices for a single question; use fields for a form")
    fields: list[HumanQuestionField] | None = Field(default=None, description="One or more form fields; each has label, kind, options and required")

    @field_validator('fields', mode='before')
    @classmethod
    def normalize_fields(cls, value):
        value = _form_items(value)
        return [value] if isinstance(value, dict) and ('label' in value or 'question' in value) else value

    @field_validator('options', mode='before')
    @classmethod
    def normalize_options(cls, value):
        return _form_options(value)


class ToolSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    description: str
    input_schema: dict[str, Any]
    roles: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_:-][A-Za-z0-9_.:-]*$")
    session_id: str = Field(min_length=1, max_length=200)
    text: str
    mode: Literal["single-agent", "workforce"] = "workforce"
    scope_ref: str
    workspace: str
    workspace_key: str = ""
    profile_revision: str = ""
    tools: list[ToolSpec] = Field(default_factory=list)
    models: dict[str, dict[str, Any]] = Field(default_factory=dict)
    instructions: str = ""
    skills: dict[str, list[str]] = Field(default_factory=dict)
    skill_routes: dict[str, str] = Field(default_factory=dict)
    memory_paths: list[str] = Field(default_factory=list)
    history: list[dict[str, Any]] = Field(default_factory=list)
    file_access: bool = True
    confirm_plan: bool = True
    # Count all model calls (including subagents); cap only when requested.
    max_steps: int | None = Field(default=None, ge=1)
    # None means usage is tracked without a cumulative task token cap.
    max_total_tokens: int | None = Field(default=None, ge=1)
    resume_execution: bool = False


class ToolInvocation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope_ref: str
    invocation_id: str
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    ticket: str | None = None


class ResumeRequest(BaseModel):
    interrupt_id: str
    value: Any
