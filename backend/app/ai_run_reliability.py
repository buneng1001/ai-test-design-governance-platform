"""AI 运行的错误分类、脱敏和有限退避策略。"""

import re


def error_category(error_code: str | None) -> str | None:
    if error_code is None:
        return None
    if error_code in {"timeout", "provider_timeout"}:
        return "timeout"
    if error_code in {"rate_limit", "provider_http_429"}:
        return "rate_limit"
    if error_code in {"temporary_error", "provider_connection_error"} or error_code.startswith("provider_http_5"):
        return "transient"
    if error_code in {"authentication_error", "provider_unavailable"} or error_code.startswith("provider_http_401"):
        return "authentication"
    if error_code == "parameter_error" or error_code.startswith("provider_http_4"):
        return "parameter"
    if error_code == "content_safety_error":
        return "content_safety"
    if error_code in {"schema_invalid", "provider_json_invalid", "provider_response_invalid", "provider_response_truncated"}:
        return "structure"
    return "provider"


def retry_delay_ms(attempt_number: int) -> int:
    return min(5000, 250 * (2 ** max(0, attempt_number - 1)))


def redact_diagnostic(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"(?i)(bearer\s+|api[_ -]?key[=:]\s*)[^\s,;]+", r"\1[REDACTED]", value)[:160]
