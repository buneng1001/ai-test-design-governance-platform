from app.ai_service import MODEL_REQUEST_TIMEOUT_SECONDS, ModelResponse
from app.model_config_service import provider_error_type, service_error


class V020RunError(Exception):
    def __init__(self, status_code: int, detail: str | dict) -> None:
        self.status_code = status_code
        self.detail = detail
        if isinstance(detail, dict):
            message = detail.get("user_message", "模型调用失败")
            action = detail.get("suggested_action")
            if action:
                message = f"{message}。建议：{action}"
        else:
            message = detail
        super().__init__(message)


def model_failure(response: ModelResponse, provider: str, model: str, page: str) -> tuple[int, dict]:
    """把模型适配器错误转换成工作台可展示、可重试的脱敏契约。"""
    error_type = provider_error_type(response.error_code)
    error = service_error("model_call", provider, model, error_type, response.error_code)
    if error_type == "timeout":
        page_label = {
            "understanding": "资料阅读整理",
            "analysis": "需求分析",
            "suggestions": "新增建议",
            "review": "审核",
            "cases": "测试用例生成",
        }[page]
        error = error.model_copy(update={
            "user_message": f"模型服务在{page_label}阶段等待 {MODEL_REQUEST_TIMEOUT_SECONDS} 秒后仍未返回",
            "suggested_action": "检查网络、VPN/代理或模型负载后重试；持续超时时可缩小输入范围或更换响应更快的模型",
        })
    return (504 if error_type == "timeout" else 502), error.model_dump(mode="json")
