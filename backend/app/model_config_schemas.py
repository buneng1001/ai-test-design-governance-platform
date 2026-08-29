from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing_extensions import Annotated


Provider = Literal["deepseek", "siliconflow", "kimi", "glm", "custom"]


class SessionModelConfigInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Provider
    model: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    base_url: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    api_key: Annotated[str, StringConstraints(min_length=1, max_length=500)]


class SessionModelConfigStatus(BaseModel):
    provider: Provider
    model: str
    base_url: str
    api_key_configured: bool


class ConnectionTestResult(BaseModel):
    success: bool
    message: str
    provider: Provider
    model: str


PROVIDER_DEFAULTS: dict[str, dict[str, object]] = {
    "deepseek": {"base_url": "https://api.deepseek.com", "models": ["deepseek-chat", "deepseek-reasoner"]},
    "siliconflow": {
        "base_url": "https://api.siliconflow.cn/v1",
        "models": ["Qwen/Qwen3-8B", "deepseek-ai/DeepSeek-V3"],
    },
    "kimi": {"base_url": "https://api.moonshot.cn/v1", "models": ["moonshot-v1-8k", "moonshot-v1-32k"]},
    "glm": {"base_url": "https://open.bigmodel.cn/api/paas/v4", "models": ["glm-4.5", "glm-4.5-air"]},
}


class ProviderOption(BaseModel):
    id: str
    name: str
    base_url: str
    models: list[str] = Field(min_length=1)
