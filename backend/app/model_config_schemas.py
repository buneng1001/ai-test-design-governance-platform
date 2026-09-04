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
    models: list[str] = Field(min_length=1)
