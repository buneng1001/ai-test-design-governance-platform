import json
from dataclasses import dataclass
from time import perf_counter
from typing import Callable


@dataclass(frozen=True)
class StreamedChatResult:
    payload: dict
    response_length: int
    first_event_ms: int | None
    duration_ms: int


class ProviderStreamCancelled(Exception):
    pass


def consume_chat_response(
    response, cancel_requested: Callable[[], bool] | None = None, max_duration_seconds: int | None = None,
) -> StreamedChatResult:
    """读取 OpenAI 兼容 SSE；测试桩或非流式降级响应仍可按完整 JSON 读取。"""
    started = perf_counter()
    if not hasattr(response, "__iter__"):
        raw = response.read()
        return StreamedChatResult(
            payload=json.loads(raw.decode("utf-8")), response_length=len(raw), first_event_ms=None,
            duration_ms=max(0, int((perf_counter() - started) * 1000)),
        )

    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    usage: dict = {}
    finish_reason: str | None = None
    response_length = 0
    first_event_ms: int | None = None
    event_count = 0
    for raw_line in response:
        if max_duration_seconds is not None and perf_counter() - started > max_duration_seconds:
            raise TimeoutError("total_timeout")
        if cancel_requested and cancel_requested():
            raise ProviderStreamCancelled
        response_length += len(raw_line)
        line = raw_line.decode("utf-8").strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        event = json.loads(data)
        event_count += 1
        if first_event_ms is None:
            first_event_ms = max(0, int((perf_counter() - started) * 1000))
        if isinstance(event.get("usage"), dict):
            usage = event["usage"]
        choices = event.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            continue
        choice = choices[0]
        if isinstance(choice.get("finish_reason"), str):
            finish_reason = choice["finish_reason"]
        delta = choice.get("delta") if isinstance(choice.get("delta"), dict) else {}
        if isinstance(delta.get("content"), str):
            content_parts.append(delta["content"])
        if isinstance(delta.get("reasoning_content"), str):
            reasoning_parts.append(delta["reasoning_content"])
    if event_count == 0:
        raise ValueError("模型流式响应中没有有效 data 事件")
    payload = {
        "choices": [{
            "finish_reason": finish_reason,
            "message": {
                "content": "".join(content_parts) or None,
                "reasoning_content": "".join(reasoning_parts) or None,
            },
        }],
        "usage": usage,
    }
    return StreamedChatResult(
        payload=payload, response_length=response_length, first_event_ms=first_event_ms,
        duration_ms=max(0, int((perf_counter() - started) * 1000)),
    )
