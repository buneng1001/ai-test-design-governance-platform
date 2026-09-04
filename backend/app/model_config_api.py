from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import json
import sqlite3
from contextlib import contextmanager
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, FastAPI, Header, HTTPException, status

from app.ai_service import MODEL_REQUEST_TIMEOUT_SECONDS, _provider_request_parameters

from app.model_config_schemas import (
    ConnectionTestResult,
    PROVIDER_DEFAULTS,
    ProviderOption,
    SessionModelConfigInput,
    SessionModelConfigStatus,
)


_DATABASE_PATH: Path | None = None


def register_model_config_routes(app: FastAPI, database_path: Path) -> None:
    global _DATABASE_PATH
    _DATABASE_PATH = database_path
    router = APIRouter()

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
        config = _read_config(x_session_id)
        return _status(config)

    @router.put("/api/ai-session-config", response_model=SessionModelConfigStatus)
    def set_session_config(
        config: SessionModelConfigInput,
        x_session_id: str | None = Header(default=None),
    ) -> SessionModelConfigStatus:
        session_id = _require_session_id(x_session_id)
        with _connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO ai_model_configs(client_id, config_json, updated_at) VALUES (?, ?, ?)",
                (session_id, config.model_dump_json(), datetime.now(UTC).isoformat()),
            )
        return to_session_config_status(config)

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
                f"{config.base_url.rstrip('/')}/chat/completions",
                data=json.dumps({
                    "model": config.model,
                    "messages": [
                        {"role": "system", "content": "只输出 JSON：{\"connected\":true}"},
                        {"role": "user", "content": "请返回连接测试 JSON。"},
                    ],
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    **_provider_request_parameters(config.provider, config.model),
                    **({"enable_thinking": False} if config.provider == "siliconflow" and any(
                        marker in config.model for marker in ("Qwen3", "DeepSeek-V3.2", "DeepSeek-V3.1")
                    ) else {}),
                }).encode("utf-8"),
                headers={"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=MODEL_REQUEST_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not payload["choices"][0]["message"]["content"]:
                raise ValueError("模型响应缺少 content")
        except HTTPError as error:
            if error.code in {401, 403}:
                message = "API Key 无效或没有当前模型的调用权限"
            elif error.code == 404:
                message = "模型或接口不存在，请检查模型名称和 Base URL"
            elif error.code == 429:
                message = "模型服务限流，请稍后重试"
            elif error.code == 400:
                message = "模型可以连接，但不接受 JSON 输出参数；请切换支持 JSON 的模型"
            else:
                message = f"模型服务返回 HTTP {error.code}"
            return ConnectionTestResult(
                success=False, message=message,
                provider=config.provider, model=config.model,
            )
        except TimeoutError:
            return ConnectionTestResult(
                success=False, message="模型连接超时，请检查网络或模型负载后重试",
                provider=config.provider, model=config.model,
            )
        except URLError:
            return ConnectionTestResult(
                success=False, message="无法连接模型服务，请检查 Base URL 和网络",
                provider=config.provider, model=config.model,
            )
        except (ValueError, KeyError, IndexError, TypeError):
            return ConnectionTestResult(
                success=False, message="模型已连接，但未返回可解析的 JSON；请确认模型支持 JSON 输出",
                provider=config.provider, model=config.model,
            )
        return ConnectionTestResult(
            success=True,
            message="真实模型连接测试成功，已完成一次实际对话调用",
            provider=config.provider,
            model=config.model,
        )

    @router.delete("/api/ai-session-config", status_code=status.HTTP_204_NO_CONTENT)
    def clear_session_config(x_session_id: str | None = Header(default=None)) -> None:
        with _connect() as connection:
            connection.execute("DELETE FROM ai_model_configs WHERE client_id = ?", (_require_session_id(x_session_id),))

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


def get_session_model_config(session_id: str | None) -> SessionModelConfigInput | None:
    """供模型调用读取持久化配置；API Key 不进入 API 响应或日志。"""

    return _read_config(session_id)


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    if _DATABASE_PATH is None:
        raise RuntimeError("模型配置数据库尚未初始化")
    connection = sqlite3.connect(_DATABASE_PATH)
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def _read_config(session_id: str | None) -> SessionModelConfigInput | None:
    if not session_id:
        return None
    with _connect() as connection:
        row = connection.execute(
            "SELECT config_json FROM ai_model_configs WHERE client_id = ?", (session_id,)
        ).fetchone()
    return SessionModelConfigInput.model_validate(json.loads(row[0])) if row else None


def _status(config: SessionModelConfigInput | None) -> SessionModelConfigStatus | None:
    if config is None:
        return None
    return to_session_config_status(config)
