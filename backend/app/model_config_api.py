"""模型配置 HTTP 边界：不向 SQLite、响应或日志传递 API Key。"""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import APIRouter, FastAPI, Header, HTTPException, status

from app.ai_service import MODEL_REQUEST_TIMEOUT_SECONDS, _provider_request_parameters
from app.model_config_schemas import (
    ConnectionTestResult, ModelDiscoveryResult, ModelOption, ProviderOption,
    SessionModelConfigInput, SessionModelConfigStatus, StoredModelConfig,
)
from app.model_config_service import (
    ResolvedModelConfig, compose_status, invalidated_verification, persist_verification,
    remember_local_credential, resolve_credential, service_error,
)


_DATABASE_PATH: Path | None = None
_LOCAL_CREDENTIALS_PATH: Path | None = None
_TEMPORARY_CREDENTIALS: dict[tuple[str, str], str] = {}


def register_model_config_routes(app: FastAPI, database_path: Path, local_credentials_path: Path) -> None:
    global _DATABASE_PATH, _LOCAL_CREDENTIALS_PATH
    _DATABASE_PATH, _LOCAL_CREDENTIALS_PATH = database_path, local_credentials_path
    router = APIRouter()

    @router.get("/api/model-providers", response_model=list[ProviderOption])
    def list_model_providers() -> list[ProviderOption]:
        from app.model_config_schemas import PROVIDER_DEFAULTS
        options = [
            ProviderOption(id=provider_id, name=name, base_url=details["base_url"],
                           models=[ModelOption(id=model, state="preset") for model in details["models"]])
            for provider_id, name, details in [
                ("deepseek", "DeepSeek", PROVIDER_DEFAULTS["deepseek"]),
                ("siliconflow", "硅基流动", PROVIDER_DEFAULTS["siliconflow"]),
                ("kimi", "Kimi", PROVIDER_DEFAULTS["kimi"]),
                ("glm", "GLM", PROVIDER_DEFAULTS["glm"]),
            ]
        ]
        options.append(ProviderOption(id="custom", name="自定义 OpenAI 兼容服务", base_url="",
                                      models=[ModelOption(id="手动输入模型", state="manual")]))
        return options

    @router.get("/api/ai-session-config", response_model=SessionModelConfigStatus | None)
    def get_session_config(x_session_id: str | None = Header(default=None)) -> SessionModelConfigStatus | None:
        session_id = _require_session_id(x_session_id)
        config = _read_stored_config(session_id)
        return _status(session_id, config) if config else None

    @router.put("/api/ai-session-config", response_model=SessionModelConfigStatus)
    def set_session_config(config: SessionModelConfigInput,
                           x_session_id: str | None = Header(default=None)) -> SessionModelConfigStatus:
        session_id = _require_session_id(x_session_id)
        stored = _store_config(session_id, config, allow_remember=True)
        return _status(session_id, stored)

    @router.post("/api/ai-session-config/models/discover", response_model=ModelDiscoveryResult)
    def discover_models(config: SessionModelConfigInput,
                        x_session_id: str | None = Header(default=None)) -> ModelDiscoveryResult:
        session_id = _require_session_id(x_session_id)
        stored = _store_config(session_id, config)
        resolved = _resolve(session_id, stored)
        if not resolved.api_key:
            return ModelDiscoveryResult(success=False, provider=stored.provider, models=[], error=service_error(
                "model_discovery", stored.provider, stored.model, "missing_credential"))
        try:
            request = Request(f"{stored.base_url.rstrip('/')}/models",
                              headers={"Authorization": f"Bearer {resolved.api_key}"}, method="GET")
            with urlopen(request, timeout=MODEL_REQUEST_TIMEOUT_SECONDS) as response:
                models = _parse_discovered_models(json.loads(response.read().decode("utf-8")))
        except HTTPError as error:
            return _discovery_failure(session_id, stored, resolved, _http_error_type(error.code), f"HTTP {error.code}")
        except TimeoutError:
            return _discovery_failure(session_id, stored, resolved, "timeout")
        except URLError:
            return _discovery_failure(session_id, stored, resolved, "connection")
        except (ValueError, KeyError, TypeError):
            return _discovery_failure(session_id, stored, resolved, "invalid_response")
        with _connect() as connection:
            connection.execute(
                """INSERT OR REPLACE INTO ai_model_discoveries(client_id, provider, base_url, models_json, discovered_at)
                VALUES (?, ?, ?, ?, ?)""",
                (session_id, stored.provider, stored.base_url, json.dumps(models), datetime.now(UTC).isoformat()),
            )
        return ModelDiscoveryResult(success=True, provider=stored.provider,
                                    models=[ModelOption(id=model, state="discovered") for model in models])

    @router.post("/api/ai-session-config/test", response_model=ConnectionTestResult)
    def test_session_config(config: SessionModelConfigInput,
                            x_session_id: str | None = Header(default=None)) -> ConnectionTestResult:
        session_id = _require_session_id(x_session_id)
        if not config.base_url.startswith(("http://", "https://")):
            raise HTTPException(status_code=422, detail="Endpoint 必须以 http:// 或 https:// 开头")
        stored = _store_config(session_id, config)
        resolved = _resolve(session_id, stored)
        if not resolved.api_key:
            return _connection_failure(session_id, stored, resolved, "missing_credential")
        try:
            request = Request(
                f"{stored.base_url.rstrip('/')}/chat/completions",
                data=json.dumps({
                    "model": stored.model,
                    "messages": [{"role": "user", "content": "Respond with JSON: {\"connected\": true}"}],
                    "temperature": 0, "response_format": {"type": "json_object"},
                    **_provider_request_parameters(stored.provider, stored.model),
                    **({"enable_thinking": False} if stored.provider == "siliconflow" and any(
                        marker in stored.model for marker in ("Qwen3", "DeepSeek-V3.2", "DeepSeek-V3.1")
                    ) else {}),
                }).encode("utf-8"),
                headers={"Authorization": f"Bearer {resolved.api_key}", "Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=MODEL_REQUEST_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not payload["choices"][0]["message"]["content"]:
                raise ValueError("empty response")
        except HTTPError as error:
            return _connection_failure(session_id, stored, resolved, _http_error_type(error.code), f"HTTP {error.code}")
        except TimeoutError:
            return _connection_failure(session_id, stored, resolved, "timeout")
        except URLError:
            return _connection_failure(session_id, stored, resolved, "connection")
        except (ValueError, KeyError, IndexError, TypeError):
            return _connection_failure(session_id, stored, resolved, "invalid_response")
        with _connect() as connection:
            persist_verification(connection, session_id, stored, resolved.credential_source, "verified")
        return ConnectionTestResult(success=True, message="模型连接测试成功", provider=stored.provider, model=stored.model)

    @router.delete("/api/ai-session-config", status_code=status.HTTP_204_NO_CONTENT)
    def clear_session_config(x_session_id: str | None = Header(default=None)) -> None:
        session_id = _require_session_id(x_session_id)
        with _connect() as connection:
            connection.execute("DELETE FROM ai_model_configs WHERE client_id = ?", (session_id,))
            connection.execute("DELETE FROM ai_model_connection_records WHERE client_id = ?", (session_id,))
            connection.execute("DELETE FROM ai_model_discoveries WHERE client_id = ?", (session_id,))
        for key in [key for key in _TEMPORARY_CREDENTIALS if key[0] == session_id]:
            del _TEMPORARY_CREDENTIALS[key]

    app.include_router(router)


def get_session_model_config(session_id: str | None) -> ResolvedModelConfig | None:
    """真实模型调用只通过这里解析 Key；数据库从不保存其原值。"""
    if not session_id:
        return None
    config = _read_stored_config(session_id)
    if config is None:
        return None
    resolved = _resolve(session_id, config)
    return resolved if resolved.api_key else None


def _store_config(session_id: str, config: SessionModelConfigInput, allow_remember: bool = False) -> StoredModelConfig:
    stored = StoredModelConfig.model_validate(config.model_dump(exclude={"api_key", "remember_api_key"}))
    if config.remember_api_key:
        if not allow_remember or not config.api_key:
            raise HTTPException(status_code=422, detail="勾选记住 API Key 时必须输入 Key")
        remember_local_credential(_credentials_path(), config.provider, config.api_key)
        _TEMPORARY_CREDENTIALS.pop((session_id, config.provider), None)
    elif config.api_key:
        _TEMPORARY_CREDENTIALS[(session_id, config.provider)] = config.api_key
    with _connect() as connection:
        previous = _read_stored_config(session_id, connection)
        connection.execute("INSERT OR REPLACE INTO ai_model_configs(client_id, config_json, updated_at) VALUES (?, ?, ?)",
                           (session_id, stored.model_dump_json(), datetime.now(UTC).isoformat()))
        if previous is None or previous.provider != stored.provider or previous.base_url != stored.base_url or previous.model != stored.model or config.api_key:
            invalidated_verification(connection, session_id, stored, force=bool(config.api_key))
    return stored


def _connection_failure(session_id: str, config: StoredModelConfig, resolved: ResolvedModelConfig,
                        error_type: str, detail: str | None = None) -> ConnectionTestResult:
    with _connect() as connection:
        persist_verification(connection, session_id, config, resolved.credential_source, "failed", error_type, detail)
    return ConnectionTestResult(success=False, provider=config.provider, model=config.model,
                                error=service_error("connection_test", config.provider, config.model, error_type, detail))


def _discovery_failure(session_id: str, config: StoredModelConfig, resolved: ResolvedModelConfig,
                       error_type: str, detail: str | None = None) -> ModelDiscoveryResult:
    with _connect() as connection:
        persist_verification(connection, session_id, config, resolved.credential_source, "failed", error_type, detail)
    return ModelDiscoveryResult(success=False, provider=config.provider, models=[],
                                error=service_error("model_discovery", config.provider, config.model, error_type, detail))


def _parse_discovered_models(payload: object) -> list[str]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("invalid model catalog")
    models = [item["id"] for item in payload["data"] if isinstance(item, dict) and isinstance(item.get("id"), str)]
    if not models:
        raise ValueError("empty model catalog")
    return list(dict.fromkeys(models))[:100]


def _http_error_type(code: int) -> str:
    if code in {401, 403}: return "authentication"
    if code == 404: return "not_found"
    if code == 429: return "rate_limit"
    if 500 <= code <= 599: return "server"
    return "invalid_configuration"


def _require_session_id(session_id: str | None) -> str:
    if not session_id or len(session_id) > 100:
        raise HTTPException(status_code=400, detail="缺少当前浏览器会话标识")
    return session_id


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


def _read_stored_config(session_id: str, connection: sqlite3.Connection | None = None) -> StoredModelConfig | None:
    if connection is None:
        with _connect() as own_connection:
            return _read_stored_config(session_id, own_connection)
    row = connection.execute("SELECT config_json FROM ai_model_configs WHERE client_id = ?", (session_id,)).fetchone()
    if not row:
        return None
    try:
        return StoredModelConfig.model_validate(json.loads(row[0]))
    except (ValueError, TypeError):
        return None


def _resolve(session_id: str, config: StoredModelConfig) -> ResolvedModelConfig:
    return resolve_credential(config, _TEMPORARY_CREDENTIALS, session_id, _credentials_path())


def _status(session_id: str, config: StoredModelConfig) -> SessionModelConfigStatus:
    resolved = _resolve(session_id, config)
    with _connect() as connection:
        return compose_status(connection, session_id, config, resolved.credential_source)


def _credentials_path() -> Path:
    if _LOCAL_CREDENTIALS_PATH is None:
        raise RuntimeError("本地凭据文件路径尚未初始化")
    return _LOCAL_CREDENTIALS_PATH
