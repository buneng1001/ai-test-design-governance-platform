"""模型配置的凭据解析、状态合成与脱敏错误转换。"""

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.model_config_schemas import (
    CredentialSource,
    ModelOption,
    ModelServiceError,
    Provider,
    PROVIDER_DEFAULTS,
    SessionModelConfigStatus,
    StoredModelConfig,
)


_KEY_VARIABLES: dict[Provider, str] = {
    "deepseek": "DEEPSEEK_API_KEY",
    "siliconflow": "SILICONFLOW_API_KEY",
    "kimi": "KIMI_API_KEY",
    "glm": "GLM_API_KEY",
    "custom": "CUSTOM_OPENAI_API_KEY",
}


@dataclass(frozen=True)
class ResolvedModelConfig:
    provider: Provider
    model: str
    base_url: str
    api_key: str
    credential_source: CredentialSource


def load_local_credentials(path: Path) -> dict[str, str]:
    """只读取项目根目录被 Git 忽略的 `.env.local`，不污染进程环境。"""
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def remember_local_credential(path: Path, provider: Provider, api_key: str) -> None:
    """只更新对应服务商的 Key，保留其他本地配置和注释。"""
    variable = _KEY_VARIABLES[provider]
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    replacement = f"{variable}={api_key}"
    replaced = False
    rendered: list[str] = []
    for line in lines:
        if line.strip().startswith(f"{variable}="):
            rendered.append(replacement)
            replaced = True
        else:
            rendered.append(line)
    if not replaced:
        rendered.append(replacement)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(rendered) + "\n", encoding="utf-8")


def resolve_credential(
    config: StoredModelConfig,
    temporary_credentials: dict[tuple[str, Provider], str],
    session_id: str,
    local_credentials_path: Path,
) -> ResolvedModelConfig:
    temporary = temporary_credentials.get((session_id, config.provider), "")
    if temporary:
        return ResolvedModelConfig(**config.model_dump(), api_key=temporary, credential_source="temporary")
    variable = _KEY_VARIABLES[config.provider]
    local_value = load_local_credentials(local_credentials_path).get(variable, "")
    if local_value:
        return ResolvedModelConfig(**config.model_dump(), api_key=local_value, credential_source="remembered_local")
    environment_value = os.getenv(variable, "")
    return ResolvedModelConfig(
        **config.model_dump(), api_key=environment_value,
        credential_source="environment" if environment_value else "none",
    )


def compose_status(
    connection: sqlite3.Connection,
    session_id: str,
    config: StoredModelConfig,
    credential_source: CredentialSource,
) -> SessionModelConfigStatus:
    verification = connection.execute(
        "SELECT status, validated_at FROM ai_model_connection_records WHERE client_id = ? AND provider = ?",
        (session_id, config.provider),
    ).fetchone()
    discovered = connection.execute(
        "SELECT models_json FROM ai_model_discoveries WHERE client_id = ? AND provider = ? AND base_url = ?",
        (session_id, config.provider, config.base_url),
    ).fetchone()
    states: dict[str, str] = {
        model: "preset" for model in PROVIDER_DEFAULTS.get(config.provider, {}).get("models", [])
    }
    if discovered:
        states.update({model: "discovered" for model in json.loads(discovered[0])})
    verification_status = verification[0] if verification else "unverified"
    if verification_status in {"verified", "failed", "invalidated"}:
        states[config.model] = verification_status
    else:
        states.setdefault(config.model, "manual")
    return SessionModelConfigStatus(
        **config.model_dump(), credential_source=credential_source,
        credential_configured=credential_source != "none",
        model_options=[ModelOption(id=model, state=state) for model, state in states.items()],
        verification_status=verification_status,
        validated_at=datetime.fromisoformat(verification[1]) if verification and verification[1] else None,
    )


def persist_verification(
    connection: sqlite3.Connection,
    session_id: str,
    config: StoredModelConfig,
    credential_source: CredentialSource,
    status: str,
    error_type: str | None = None,
    detail: str | None = None,
) -> None:
    connection.execute(
        """INSERT OR REPLACE INTO ai_model_connection_records(
            client_id, provider, base_url, model, status, credential_source, validated_at, error_type, detail
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (session_id, config.provider, config.base_url, config.model, status, credential_source,
         datetime.now(UTC).isoformat() if status == "verified" else None, error_type, detail),
    )


def invalidated_verification(
    connection: sqlite3.Connection, session_id: str, config: StoredModelConfig, *, force: bool = False,
) -> None:
    previous = connection.execute(
        "SELECT base_url, model FROM ai_model_connection_records WHERE client_id = ? AND provider = ?",
        (session_id, config.provider),
    ).fetchone()
    if previous and (force or tuple(previous) != (config.base_url, config.model)):
        persist_verification(connection, session_id, config, "none", "invalidated")


def service_error(stage: str, provider: str, model: str, error_type: str, detail: str | None = None) -> ModelServiceError:
    rules = {
        "authentication": (False, "API Key 无效或没有当前模型的调用权限", "检查该服务商的 API Key 和账号权限"),
        "not_found": (False, "模型或接口不存在", "检查 Endpoint 和模型名称，或手动输入可用模型"),
        "rate_limit": (True, "模型服务限流", "稍后重试，或减少本次请求规模"),
        "invalid_response": (False, "模型服务返回了无法解析的响应", "确认模型支持当前 OpenAI 兼容接口"),
        "invalid_configuration": (False, "模型配置无效", "检查 Endpoint、模型名称和 API Key"),
        "timeout": (True, "模型服务连接超时", "检查网络或模型负载后重试"),
        "connection": (True, "无法连接模型服务", "检查 Endpoint、网络、VPN 或代理"),
        "server": (True, "模型服务暂时不可用", "稍后重试"),
        "missing_credential": (False, "未找到当前服务商的 API Key", "输入临时 Key，或在本地凭据配置中保存该服务商的 Key"),
    }
    retryable, user_message, suggested_action = rules.get(error_type, rules["server"])
    return ModelServiceError(
        stage=stage, provider=provider, model=model, error_type=error_type, retryable=retryable,
        user_message=user_message, suggested_action=suggested_action, detail=detail,
    )


def provider_error_type(error_code: str | None) -> str:
    """将现有模型适配器的错误码归一到公开的失败契约。"""
    if error_code in {"authentication_error", "provider_http_401", "provider_http_403"}:
        return "authentication"
    if error_code in {"parameter_error", "provider_http_400"}:
        return "invalid_configuration"
    if error_code == "provider_http_404":
        return "not_found"
    if error_code in {"timeout", "provider_timeout", "provider_http_408"}:
        return "timeout"
    if error_code in {"rate_limit", "provider_http_429"}:
        return "rate_limit"
    if error_code == "provider_connection_error":
        return "connection"
    if error_code in {"provider_response_invalid", "provider_json_invalid", "provider_response_truncated"}:
        return "invalid_response"
    return "server"
