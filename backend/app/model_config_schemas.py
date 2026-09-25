from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing_extensions import Annotated


Provider = Literal["deepseek", "siliconflow", "kimi", "glm", "custom"]
CredentialSource = Literal["temporary", "remembered_local", "environment", "none"]
ModelState = Literal["preset", "discovered", "verified", "failed", "invalidated", "manual"]


class SessionModelConfigInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Provider
    model: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    base_url: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    api_key: Annotated[str, StringConstraints(max_length=500)] = ""
    remember_api_key: bool = False


class StoredModelConfig(BaseModel):
    """允许写入业务数据库的模型元数据；绝不包含凭据。"""

    model_config = ConfigDict(extra="forbid")

    provider: Provider
    model: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    base_url: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class ModelOption(BaseModel):
    id: str
    state: ModelState


class SessionModelConfigStatus(BaseModel):
    provider: Provider
    model: str
    base_url: str
    credential_source: CredentialSource
    credential_configured: bool
    model_options: list[ModelOption]
    verification_status: Literal["unverified", "verified", "failed", "invalidated"] = "unverified"
    validated_at: datetime | None = None


class ConnectionTestResult(BaseModel):
    success: bool
    message: str | None = None
    provider: Provider
    model: str
    error: "ModelServiceError | None" = None


class ModelServiceError(BaseModel):
    """可用于连接、发现和模型调用的脱敏失败契约。"""

    stage: Literal["connection_test", "model_discovery", "model_call"]
    provider: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
    model: str
    error_type: str
    retryable: bool
    user_message: str
    suggested_action: str
    detail: str | None = None


class ModelDiscoveryResult(BaseModel):
    success: bool
    provider: Provider
    models: list[ModelOption]
    error: ModelServiceError | None = None


PROVIDER_DEFAULTS: dict[str, dict[str, object]] = {
    "deepseek": {"base_url": "https://api.deepseek.com", "models": ["deepseek-v4-flash", "deepseek-v4-pro"]},
    "siliconflow": {
        "base_url": "https://api.siliconflow.cn/v1",
        "models": [
            "Qwen/Qwen2.5-72B-Instruct", "zai-org/GLM-5.2", "zai-org/GLM-4.5V",
            "Pro/moonshotai/Kimi-K2.6", "MiniMaxAI/MiniMax-M2.5", "deepseek-ai/DeepSeek-V3.2",
            "Qwen/Qwen3.6-27B", "Qwen/Qwen3.5-27B", "Qwen/Qwen3-8B",
        ],
    },
    "kimi": {"base_url": "https://api.moonshot.cn/v1", "models": ["kimi-k2.6", "kimi-k2.5", "kimi-k2.7-code"]},
    "glm": {"base_url": "https://open.bigmodel.cn/api/paas/v4", "models": ["glm-4.5", "glm-4.5-air"]},
}


class ProviderOption(BaseModel):
    id: str
    name: str
    base_url: str
    models: list[ModelOption] = Field(min_length=1)
