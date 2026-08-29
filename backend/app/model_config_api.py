from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import APIRouter, FastAPI, Header, HTTPException, status

from app.model_config_schemas import (
    ConnectionTestResult,
    PROVIDER_DEFAULTS,
    ProviderOption,
    SessionModelConfigInput,
    SessionModelConfigStatus,
)


def register_model_config_routes(app: FastAPI) -> None:
    router = APIRouter()
    session_configs: dict[str, SessionModelConfigStatus] = {}

    @router.get("/api/model-providers", response_model=list[ProviderOption])
    def list_model_providers() -> list[ProviderOption]:
        options = [
            ProviderOption(id=provider_id, name=name, **details)
            for provider_id, name, details in [
                ("deepseek", "DeepSeek", PROVIDER_DEFAULTS["deepseek"]),
                ("siliconflow", "硅基流动", PROVIDER_DEFAULTS["siliconflow"]),
                ("kimi", "Kimi", PROVIDER_DEFAULTS["kimi"]),
                ("glm", "GLM", PROVIDER_DEFAULTS["glm"]),
            ]
        ]
        options.append(ProviderOption(id="custom", name="自定义供应商", base_url="", models=["自定义模型"]))
        return options

    @router.get("/api/ai-session-config", response_model=SessionModelConfigStatus | None)
    def get_session_config(x_session_id: str | None = Header(default=None)) -> SessionModelConfigStatus | None:
        config = session_configs.get(x_session_id or "")
        return _status(config)

    @router.put("/api/ai-session-config", response_model=SessionModelConfigStatus)
    def set_session_config(
        config: SessionModelConfigInput,
        x_session_id: str | None = Header(default=None),
    ) -> SessionModelConfigStatus:
        session_id = _require_session_id(x_session_id)
        result = to_session_config_status(config)
        session_configs[session_id] = result
        return result

    @router.post("/api/ai-session-config/test", response_model=ConnectionTestResult)
    def test_session_config(
        config: SessionModelConfigInput,
        x_session_id: str | None = Header(default=None),
    ) -> ConnectionTestResult:
        _require_session_id(x_session_id)
        if not config.base_url.startswith(("http://", "https://")):
            raise HTTPException(status_code=422, detail="Base URL 必须以 http:// 或 https:// 开头")
        try:
            request = Request(
                f"{config.base_url.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {config.api_key}"},
            )
            with urlopen(request, timeout=5):
                pass
        except HTTPError as error:
            return ConnectionTestResult(
                success=False, message=f"模型服务返回 HTTP {error.code}",
                provider=config.provider, model=config.model,
            )
        except URLError:
            return ConnectionTestResult(
                success=False, message="无法连接模型服务，请检查 Base URL 和网络",
                provider=config.provider, model=config.model,
            )
        return ConnectionTestResult(
            success=True,
            message="配置格式有效；真实模型连接将在发起模型调用时使用当前会话密钥",
            provider=config.provider,
            model=config.model,
        )

    @router.delete("/api/ai-session-config", status_code=status.HTTP_204_NO_CONTENT)
    def clear_session_config(x_session_id: str | None = Header(default=None)) -> None:
        session_configs.pop(_require_session_id(x_session_id), None)

    app.include_router(router)


def _require_session_id(session_id: str | None) -> str:
    if not session_id or len(session_id) > 100:
        raise HTTPException(status_code=400, detail="缺少当前浏览器会话标识")
    return session_id


def to_session_config_status(config: SessionModelConfigInput) -> SessionModelConfigStatus:
    return SessionModelConfigStatus(
        provider=config.provider,
        model=config.model,
        base_url=config.base_url,
        api_key_configured=True,
    )


def _status(config: SessionModelConfigStatus | None) -> SessionModelConfigStatus | None:
    if config is None:
        return None
    return config
