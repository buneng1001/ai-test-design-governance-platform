from dataclasses import dataclass
from time import sleep

from app.ai_schemas import AIModelConfig
from app.ai_service import ModelRequest
from app.v020_model_errors import V020RunError, model_failure
from app.v020_skill_batching import SkillStageBatch
from app.v020_skill_contracts import (
    SKILL_PROMPT_VERSION,
    SKILL_RETRY_BACKOFF_SECONDS,
    SKILL_STAGE_OUTPUT_TOKENS,
    StageDefinition,
)


@dataclass
class SkillModelRunner:
    model_service: object
    repository: object
    resolved: object
    run: dict
    preflight: dict

    def call(
        self,
        stage: StageDefinition,
        position: int,
        batch: SkillStageBatch,
        prompt: str,
        *,
        operation: str = "generate",
        allow_truncated: bool = True,
    ):
        response = None
        for attempt in range(1, 3):
            self.ensure_not_cancelled()
            self._ensure_request_budget()
            response = self.model_service.complete(self._request(stage, prompt, operation))
            self._record_attempt(response, position, stage.stage_id, attempt, batch, operation)
            if not response.error_code:
                return response
            if response.error_code == "provider_response_truncated" and allow_truncated:
                return response
            if response.error_code == "provider_cancelled":
                self._raise_cancelled()
            if not response.retryable or attempt == 2:
                self.raise_failure(response)
            self._bounded_backoff()
        assert response is not None
        return response

    def ensure_not_cancelled(self) -> None:
        current = self.repository.get_run(self.run["project_id"], self.run["id"]) or {}
        if current.get("cancel_requested"):
            self.run["cancel_requested"] = True
            self._raise_cancelled()

    def raise_failure(self, response) -> None:
        status, detail = model_failure(
            response, self.preflight["provider"], self.preflight["model"], "analysis",
        )
        raise V020RunError(status, detail)

    def _request(self, stage: StageDefinition, prompt: str, operation: str) -> ModelRequest:
        suffix = ".repair" if operation == "schema_repair" else ""
        return ModelRequest(
            task_type="requirement_review",
            prompt_version=f"{SKILL_PROMPT_VERSION}.{stage.stage_id.lower()}{suffix}",
            model_parameters=AIModelConfig(
                provider=self.resolved.provider,
                model=self.resolved.model,
                temperature=0,
                max_tokens=SKILL_STAGE_OUTPUT_TOKENS,
            ),
            input_asset_versions=(),
            scenario="normal",
            base_url=self.resolved.base_url,
            api_key=self.resolved.api_key,
            prompt_override=prompt,
            network_mode=self.resolved.network_mode,
            cancel_requested=self._cancel_requested,
        )

    def _ensure_request_budget(self) -> None:
        limit = int(self.run.get("max_request_count") or 0)
        if limit and len(self.run.get("attempts", [])) >= limit:
            raise V020RunError(
                422,
                f"本次需求分析已达到确认前展示的 {limit} 次模型调用硬上限；"
                "已完成批次均已保存，请缩小输入范围或选择更高输出能力的模型后继续。",
            )

    def _record_attempt(self, response, position: int, stage_id: str, attempt: int,
                        batch: SkillStageBatch, operation: str) -> None:
        self.run["attempts"].append({
            "unit": position,
            "stage_id": stage_id,
            "batch_scope_ids": list(batch.scope_ids),
            "attempt": attempt,
            "operation": operation,
            "error_code": response.error_code,
            "duration_ms": response.duration_ms,
            "first_event_ms": response.first_event_ms,
            "finish_reason": response.finish_reason,
            "response_length": response.response_length,
            "diagnostic": response.diagnostic,
        })
        self.repository.update_run(self.run)

    def _bounded_backoff(self) -> None:
        remaining = SKILL_RETRY_BACKOFF_SECONDS
        while remaining > 0:
            self.ensure_not_cancelled()
            interval = min(0.1, remaining)
            sleep(interval)
            remaining -= interval

    def _cancel_requested(self) -> bool:
        current = self.repository.get_run(self.run["project_id"], self.run["id"]) or {}
        cancelled = bool(current.get("cancel_requested"))
        if cancelled:
            self.run["cancel_requested"] = True
        return cancelled

    @staticmethod
    def _raise_cancelled() -> None:
        raise V020RunError(409, "本次运行已停止；已完成批次和阶段已保留，可稍后继续。")
