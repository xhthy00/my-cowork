"""Desktop-only model configuration. Credentials never leave this endpoint in responses."""
import hmac
import os

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, SecretStr

from app.llm.model_config import ModelConfig

router = APIRouter()


class RuntimeModel(BaseModel):
    id: str
    provider: str
    model: str
    api_key: SecretStr = Field(repr=False)
    base_url: str | None = None
    context_window: int = Field(default=200000, ge=1024)
    input_limit: int | None = Field(default=None, ge=1)
    output_limit: int = Field(default=8192, ge=1)
    compaction_ratio: float = Field(default=0.8, ge=0.1, le=0.95)
    allowed_efforts: tuple[str, ...] = ()
    allow_thinking_toggle: bool = False
    budget_min: int | None = None
    budget_max: int | None = None
    reasoning_mode: str = "default"
    reasoning_effort: str | None = None
    thinking_enabled: bool | None = None
    thinking_budget: int | None = Field(default=None, ge=0)


class RegistryUpdate(BaseModel):
    models: list[RuntimeModel]
    active_id: str | None = None


@router.post("/api/internal/models")
async def replace_models(request: Request):
    # Authenticate before parsing so even invalid payloads cannot echo a secret in 422 details.
    token = os.environ.get("MY_COWORK_MODEL_TOKEN", "")
    supplied = request.headers.get("x-model-token", "")
    if not token or not hmac.compare_digest(token, supplied):
        raise HTTPException(403, "仅桌面主进程可以同步模型")
    try:
        body = RegistryUpdate.model_validate(await request.json())
        configs = [ModelConfig(**{**item.model_dump(exclude={"api_key"}),
                                  "api_key": item.api_key.get_secret_value()}) for item in body.models]
        registry = request.app.state.task_manager.model_registry
        if registry is None:
            raise ValueError("registry unavailable")
        registry.replace(configs, body.active_id)
    except (ValueError, TypeError):
        raise HTTPException(400, "模型配置无效，原配置未更改") from None
    return {"ok": True}
