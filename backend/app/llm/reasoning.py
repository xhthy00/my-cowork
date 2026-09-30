"""Small, explicit wire adapters. An unset selection leaves vendor defaults intact."""
from app.llm.model_config import ModelConfig


def reasoning_kwargs(config: ModelConfig) -> dict:
    mode = config.reasoning_mode
    effort, enabled, budget = config.reasoning_effort, config.thinking_enabled, config.thinking_budget
    if mode == "openai-responses":
        return {"use_responses_api": True, **({"reasoning": {"effort": effort}} if effort else {})}
    if effort is None and enabled is None and budget is None:
        return {}
    if mode == "openai":
        return {"reasoning_effort": effort} if effort else {}
    if mode == "anthropic":
        result: dict = {}
        if budget is not None:
            result["thinking"] = {"type": "enabled", "budget_tokens": budget}
        if effort:
            result["output_config"] = {"effort": effort}
        if enabled is False:
            result["thinking"] = {"type": "disabled"}
        elif enabled is True and "thinking" not in result:
            result["thinking"] = ({"type": "enabled", "budget_tokens": min(4096, config.output_limit - 1)} if config.budget_min is not None else {"type": "adaptive"})
        return result
    extra: dict = {}
    if mode == "google":
        if effort is not None:
            return {"reasoning_effort": effort}
        extra["extra_body"] = {"google": {"thinking_config": {"thinking_budget": 0 if enabled is False else budget if budget is not None else -1}}}
    elif mode == "minimax":
        if enabled is not None:
            extra["thinking"] = {"type": "adaptive" if enabled else "disabled"}
        if effort is not None:
            extra["reasoning_effort"] = effort
    elif mode == "openrouter":
        extra["reasoning"] = {k: v for k, v in {"effort": effort, "enabled": enabled, "max_tokens": budget}.items() if v is not None}
    elif mode == "qwen":
        if enabled is not None:
            extra["enable_thinking"] = enabled
        if budget is not None:
            extra["thinking_budget"] = budget
            extra.setdefault("enable_thinking", True)
        if effort is not None:
            extra["reasoning_effort"] = effort
    elif mode in {"deepseek", "moonshot", "thinking"}:
        if enabled is not None or effort is not None:
            extra["thinking"] = {"type": "disabled" if enabled is False else "enabled"}
        if effort is not None:
            if mode == "moonshot":
                extra["thinking"]["effort"] = effort
            else:
                extra["reasoning_effort"] = effort
    else:
        raise ValueError("未配置此服务的思考参数协议")
    return {"extra_body": extra}
