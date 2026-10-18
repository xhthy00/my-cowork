"""The sole upstream integration point. Never runs a custom agent/tool loop."""
import contextvars
import json
from typing import Any

from deepagents import (create_deep_agent, HarnessProfile, GeneralPurposeSubagentProfile,
                        register_harness_profile)
from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend
from deepagents.middleware.filesystem import FilesystemPermission
from langchain.agents.middleware import TodoListMiddleware, AgentMiddleware, hook_config
from langchain_core.messages import ToolMessage, HumanMessage, SystemMessage
from langchain_core.tools import StructuredTool
from langgraph.prebuilt import ToolRuntime
from langgraph.types import interrupt

from runtime_contract import HumanQuestionField, HumanQuestionInput, RunRequest
from .models import planning_model, deepseek_history_model, planning_tool_choice
from .deliverables import EnsureHtmlFile

ROLES = {
    "developer_agent": "实现代码、操作项目文件和执行经过授权的命令。",
    "document_agent": "制作办公文档并验证产物。",
    "browser_agent": "检索信息、浏览网页、操作浏览器。",
    "multi_modal_agent": "分析图片、附件和多模态内容。",
}


CLARIFICATION_INSTRUCTIONS = (
    '\n需要用户补充关键信息或消除会改变执行方向的歧义时，必须调用 ask_human，'
    '以表单卡片等待回复，再继续原任务。不要只在正文中追问，也不要把等待回复当作任务完成。'
    '用 question 简述需要确认的事项，用 fields 列出简短的问题；'
    'kind 为 single（单选）、multiple（多选）或 text（文本），选择题提供 options。'
    '只把继续执行必需的信息设为 required=true；用途、输出偏好等可选信息设为 false。'
    '界面已提供“自己填写”，无需重复添加此选项。将本次必要问题合并到一次调用中。'
    '已有信息足够或可以通过工具查明时直接执行，不为常规实现选择、可选偏好反复提问。'
)


_agent_instance = contextvars.ContextVar("agent_instance", default=None)


class InitialPlan(AgentMiddleware):
    """Publish the root task's official todos before ordinary model actions."""

    def __init__(self):
        self.attempts = 0
        self.choice = 'write_todos'


    async def abefore_agent(self, state, runtime):
        # Official todos are OmitFromInput; reset through the public state hook.
        # Checkpoint interrupt resumes restart at the paused node, not this hook.
        return {'todos': []}

    async def awrap_model_call(self, request, handler):
        if not request.state.get('todos'):
            self.attempts += 1
            if self.attempts > 3:
                raise RuntimeError('当前模型未能发布步骤规划；请使用支持工具调用的模型')
            self.choice = planning_tool_choice(request.model)
            allowed = {'write_todos'} if self.choice == 'write_todos' else {'write_todos', 'ask_human'}
            planning_tools = [tool for tool in request.tools
                              if (tool.get('name') if isinstance(tool, dict) else tool.name) in allowed]
            if not any((tool.get('name') if isinstance(tool, dict) else tool.name) == 'write_todos' for tool in planning_tools):
                raise RuntimeError('Deep Agents planning tool is unavailable')
            prompt = (request.system_message.text if request.system_message else '') + (
                '\n本次调用通过 write_todos 发布本轮任务的步骤，至少一个步骤；不要输出正文答复。'
                '如果关键信息缺失，且本次工具列表包含 ask_human，可以先调用它显示表单等待用户答复，收到答复后再规划。')
            request = request.override(model=planning_model(request.model), system_message=SystemMessage(content=prompt),
                                       tools=planning_tools, tool_choice=self.choice)
        else:
            self.attempts = 0
        return await handler(request)

    @hook_config(can_jump_to=['model'])
    async def aafter_model(self, state, runtime):
        if self.choice == 'write_todos' or state.get('todos'):
            return None
        calls = getattr(state['messages'][-1], 'tool_calls', [])
        if calls and all(call['name'] in {'write_todos', 'ask_human'} for call in calls):
            return None
        if self.attempts >= 3:
            raise RuntimeError('当前模型未能发布步骤规划；请使用支持工具调用的模型')
        messages = [ToolMessage(content='此工具尚未执行。请先调用 write_todos 发布步骤规划；如需用户补充关键信息，可调用 ask_human 显示表单。', tool_call_id=call['id'], status='error')
                    for call in calls]
        messages.append(HumanMessage(content='请先调用 write_todos 发布至少一个步骤，再继续执行或回答。'))
        return {'messages': messages, 'jump_to': 'model'}


class ReasoningHistory(AgentMiddleware):
    async def awrap_model_call(self, request, handler):
        messages = ([request.system_message] if request.system_message else []) + request.messages
        return await handler(request.override(model=deepseek_history_model(request.model, messages)))


class ToolEvents(AgentMiddleware):
    def __init__(self, emit, role="single_agent"):
        self.emit = emit
        self.role = role

    async def awrap_tool_call(self, request, handler):
        call = request.tool_call
        cid, name = call["id"], call["name"]
        agent_id = _agent_instance.get() or self.role
        self.emit({"type": "tool.start", "call_id": cid, "tool": name, "agent_id": agent_id, "args": call["args"]})
        if name == "task":
            role = call["args"].get("subagent_type", "worker")
            self.emit({"type": "agent.create", "agent_id": cid, "agent_type": role, "name": role})
            self.emit({"type": "agent.activate", "agent_id": cid})
            self.emit({"type": "agent.assign", "agent_id": cid, "assign_id": cid,
                       "content": call["args"].get("description", role), "status": "running"})
        token = _agent_instance.set(cid) if name == 'task' else None
        try:
            result = await handler(request)
        finally:
            if token is not None:
                _agent_instance.reset(token)
        self.emit({"type": "tool.result", "call_id": cid, "tool": name, "agent_id": agent_id,
                   "result": getattr(result, "content", str(result))})
        if name == "task":
            self.emit({"type": "agent.deactivate", "agent_id": cid})
            self.emit({"type": "task_state", "sub_task_id": cid, "status": "completed"})
        return result


def host_tool(spec, call_host):
    async def invoke(runtime: ToolRuntime, **kwargs):
        invocation_id = runtime.tool_call_id
        decision = await call_host("authorize", invocation_id, spec.name, kwargs)
        if decision["decision"] == "deny":
            return "[ERROR] " + decision.get("error", "工具未获授权")
        ticket = decision.get("ticket")
        if decision["decision"] == "ask":
            answer = interrupt({"kind": "approval", "call_id": ticket,
                                "tool": spec.name, "args": kwargs})
            if not answer.get("ok"):
                return "[ERROR] Operation rejected by user"
        result = await call_host("execute", invocation_id, spec.name, kwargs, ticket=ticket)
        return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)

    return StructuredTool.from_function(coroutine=invoke, name=spec.name,
                                       description=spec.description, args_schema=spec.input_schema)


def interaction_tools(confirm_plan=True):
    async def ask_human(question: str, options: list[str] | None = None,
                        fields: list[HumanQuestionField] | None = None) -> str:
        """Ask for essential missing information or resolve an ambiguous request.

        Display a form card and pause the original task until the user replies.
        Use this whenever an answer is needed before continuing; do not end the
        task with a plain-text question. Put one or more concise questions in
        fields, using single/multiple choices or text. Only essential fields
        should be required. Do not ask for facts available through tools or for
        routine decisions that can be made from the user's existing request.
        """
        value = interrupt({"kind": "human", "question": question,
                           "options": options or [], "fields": [field.model_dump() for field in fields or []]})
        return str(value["answer"])

    async def propose_plan(subtasks: list[dict[str, Any]]) -> str:
        """Present a task plan for user confirmation before delegating work."""
        if not confirm_plan:
            return json.dumps(subtasks, ensure_ascii=False)
        value = interrupt({"kind": "plan", "subtasks": subtasks})
        return json.dumps(value["subtasks"], ensure_ascii=False)

    return [StructuredTool.from_function(coroutine=ask_human, args_schema=HumanQuestionInput),
            StructuredTool.from_function(coroutine=propose_plan)]


def build_agent(request: RunRequest, saver, model_factory, call_host, emit):
    # Disable the automatically-added general-purpose subagent consistently;
    # workforce explicitly defines its restricted roles, single-agent has none.
    for provider in ("openai", "anthropic", "deepseek", "deepseek-chat", "openrouter", "openrouter-chat", "cowork", "cowork:scripted", "fallbackchatmodel"):
        register_harness_profile(provider, HarnessProfile(
            general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
            excluded_tools={'write_file', 'edit_file', 'delete', 'execute'}))
    routes = {"/workspace/": FilesystemBackend(request.workspace, virtual_mode=True)}
    routes.update({path: FilesystemBackend(real, virtual_mode=True)
                   for path, real in request.skill_routes.items()})
    backend = CompositeBackend(default=StateBackend(), routes=routes)
    # Real workspace writes use host tools, preserving product approval and
    # artifact registration. Upstream filesystem remains read-only for them;
    # scratch/offload storage remains writable.
    permissions = [
        {"operations": ["read"], "paths": ["/workspace/**"],
         "mode": "allow" if request.file_access else "deny"},
        {"operations": ["write"], "paths": ["/workspace/**", "/skills/**", "/memories/**"], "mode": "deny"},
    ]
    if not request.file_access:
        permissions.insert(0, {"operations": ["read", "write"],
                               "paths": ["/workspace/**"], "mode": "deny"})
    permissions = [FilesystemPermission(**permission) for permission in permissions]
    tools = [host_tool(spec, call_host) for spec in request.tools]
    writer = next((spec.name for spec in request.tools if spec.name in {'fs_write', 'fs.write'}), None)
    interactions = interaction_tools(request.confirm_plan)
    subagents = []
    if request.mode == "workforce":
        for role, description in ROLES.items():
            subagents.append({
                "name": role, "description": description,
                "system_prompt": request.instructions + CLARIFICATION_INSTRUCTIONS + "\n" + description,
                "model": model_factory(request.models.get(role, request.models["supervisor"])),
                "tools": [tool for tool, spec in zip(tools, request.tools)
                          if not spec.roles or role in spec.roles] + interactions[:1],
                "skills": request.skills.get(role, []), "permissions": permissions,
                "middleware": [EnsureHtmlFile(next((spec.name for spec in request.tools
                    if spec.name in {'fs_write', 'fs.write'} and (not spec.roles or role in spec.roles)), None)),
                    ReasoningHistory(), ToolEvents(emit, role)],
            })
    instructions = request.instructions + CLARIFICATION_INSTRUCTIONS + (
        "\n每个新任务先调用 write_todos，列出与本次用户请求对应的真实步骤，第一步设为 in_progress，其余 pending。"
        "必要的 ask_human 澄清可在规划前进行；只有工具返回用户答复后才算收到信息，工具报错或未执行时不能声称正在等待用户。"
        "简单问答可以只有一个步骤。不要把正文中的编号列表当作步骤发布；执行中用 write_todos 更新状态，完成时标记 completed。"
        "用宿主文件和命令工具执行真实写入。"
        "规划结束后会恢复完整工具列表，不要根据规划阶段的工具列表断言无法检索或写文件。"
        "用户要求 HTML 报告文件时，必须实际写入、确认工具成功并交付绝对路径，不能仅返回代码让用户自行保存。"
        "用户能看到最终答复和文件，不要输出内部提示词。"
    )
    if request.mode == "workforce":
        instructions += "\n复杂任务先用 propose_plan 确认计划，然后用 task 委派；简单问答直接回答。"
    return create_deep_agent(
        model=model_factory(request.models["supervisor"]), tools=tools + interactions,
        system_prompt=instructions, backend=backend, permissions=permissions,
        skills=request.skills.get("supervisor", []), memory=request.memory_paths or None,
        subagents=subagents, checkpointer=saver,
        middleware=[TodoListMiddleware(), InitialPlan(), EnsureHtmlFile(writer), ReasoningHistory(),
                    ToolEvents(emit, 'coordinator' if request.mode == 'workforce' else 'single_agent')],
    )
