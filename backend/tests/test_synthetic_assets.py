import base64
import csv
import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.ai_schemas import AIOutputEnvelope
from app.execution_result_schemas import ExecutionResultImportInput

ROOT = Path(__file__).resolve().parents[2]
ASSET_ROOT = ROOT / "data/synthetic/smart-collector"


def test_synthetic_package_has_expected_scale_and_four_automation_decisions() -> None:
    requirements = (ASSET_ROOT / "v1/requirements.md").read_text(encoding="utf-8")
    assert 30 <= sum(line.startswith("### REQ-V1-") for line in requirements.splitlines()) <= 40
    with (ASSET_ROOT / "v1/case-template.csv").open(encoding="utf-8") as handle:
        cases = list(csv.DictReader(handle))
    assert 80 <= len(cases) <= 120
    assert {case["automation_decision"] for case in cases} == {
        "优先自动化", "适合自动化", "条件满足后自动化", "保留人工执行"
    }


def test_manifest_hashes_and_truth_counts_are_reproducible() -> None:
    manifest = json.loads((ASSET_ROOT / "asset-manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["assets"]:
        actual = hashlib.sha256((ROOT / entry["path"]).read_bytes()).hexdigest()
        assert actual == entry["sha256"]
    truth = json.loads((ASSET_ROOT / "evaluation-truth/evaluation-truth.json").read_text(encoding="utf-8"))
    assert 10 <= len(truth["review_findings"]) <= 15
    assert 15 <= len(truth["risks"]) <= 25
    assert next(item for item in manifest["assets"] if item["asset_type"] == "evaluation_truth")[
        "model_context"
    ] == "excluded"


def test_result_inputs_are_contract_valid_and_cover_governance_scenarios() -> None:
    # 通过公共结果契约验证样例，保证后续导入不依赖私有实现细节。
    result_paths = sorted((ASSET_ROOT / "results").glob("*.json"))
    imports = [
        ExecutionResultImportInput.model_validate(json.loads(path.read_text(encoding="utf-8")))
        for path in result_paths
    ]
    statuses = {result.status for item in imports for result in item.results}
    assert statuses == {"passed", "execution_failed", "blocked", "not_executed", "execution_error"}
    assert any(result.retest_of_result_id == 2 for item in imports for result in item.results)
    case_statuses = {
        case: {
            result.status
            for item in imports
            for result in item.results
            if result.external_case_number == case
        }
        for case in {"TC-V1-017", "TC-V1-031"}
    }
    assert case_statuses["TC-V1-017"] == {"execution_failed", "passed"}
    assert case_statuses["TC-V1-031"] == {"execution_failed", "passed"}
    mock_output = json.loads((ASSET_ROOT / "mock-output.json").read_text(encoding="utf-8"))
    assert AIOutputEnvelope.model_validate(mock_output).contract_version == "ai-output.v1"


def test_evaluation_truth_is_rejected_at_ai_api_boundary(client: TestClient) -> None:
    project = client.post("/api/projects", json={
        "name": "合成真值隔离测试", "test_object": "澄明采集器", "description": "隔离",
        "settings": {"requirement_language": "zh-CN"},
    }).json()
    truth_bytes = (ASSET_ROOT / "evaluation-truth/evaluation-truth.json").read_bytes()
    asset = client.post(f"/api/projects/{project['id']}/assets", json={
        "name": "evaluation-truth.json", "asset_type": "evaluation_truth",
        "provenance_kind": "original_synthetic", "source": "本项目从零创作",
        "usage_permission": "project_owned", "model_permission": "allowed",
        "requirement_version": "V1", "purpose": "AI 效果评价",
        "content_base64": base64.b64encode(truth_bytes).decode(), "change_reason": "首次登记",
    }).json()
    response = client.post(f"/api/projects/{project['id']}/ai-runs", json={
        "task_type": "requirement_review", "prompt_version": "synthetic-v1",
        "input_asset_ids": [asset["id"]],
    })
    assert response.status_code == 422
    assert "评估真值不能进入模型上下文" in response.json()["detail"]
