import base64
import json

from test_ai_runs_api import create_asset, create_project, run_input


def test_independent_evaluation_reproducibly_reports_truth_hits_omissions_and_expansions(client) -> None:
    project_id = create_project(client)
    input_asset_id = create_asset(client, project_id)
    truth_asset_id = create_asset(
        client,
        project_id,
        name="evaluation-truth.json",
        asset_type="evaluation_truth",
        purpose="独立评价 AI 输出",
        content_base64=base64.b64encode(json.dumps({
            "contract_version": "evaluation-truth.v1",
            "items": [
                {
                    "truth_id": "TRUTH-001",
                    "category": "review_finding",
                    "key": "Mock 对 requirement_review 的确定性候选",
                },
                {"truth_id": "TRUTH-002", "category": "key_scope", "key": "明确的关键范围缺失"},
            ],
            "distractors": [{"id": "D-1", "text": "scope_analysis", "reason": "测试无依据扩展"}],
        }, ensure_ascii=False).encode()).decode(),
    )
    hit = client.post(
        f"/api/projects/{project_id}/ai-runs", json=run_input(input_asset_id)
    ).json()
    unmatched = client.post(
        f"/api/projects/{project_id}/ai-runs",
        json=run_input(input_asset_id, task_type="scope_analysis"),
    ).json()
    truth_key = hit["output"]["items"][0]["summary"]
    payload = {
        "truth_asset_id": truth_asset_id,
        "ai_run_ids": [unmatched["id"], hit["id"]],
    }
    first = client.post(f"/api/projects/{project_id}/ai-evaluations", json=payload)
    assert first.status_code == 201, first.text
    result = first.json()
    assert result["contract_version"] == "ai-evaluation.v1"
    assert result["metrics"]["truth_hit"] == {"numerator": 1, "denominator": 2, "percentage": 50.0}
    assert result["metrics"]["key_omissions"] == {"numerator": 1, "denominator": 2, "percentage": 50.0}
    assert result["metrics"]["unsupported_expansions"] == {
        "numerator": 1, "denominator": 2, "percentage": 50.0,
    }
    assert result["metrics"]["distractor_hits"] == {"numerator": 1, "denominator": 1, "percentage": 100.0}
    assert result["unmatched_output_candidate_ids"]
    assert truth_key not in first.text

    repeated = client.post(f"/api/projects/{project_id}/ai-evaluations", json=payload).json()
    assert repeated["input_sha256"] == result["input_sha256"]
    assert repeated["metrics"] == result["metrics"]
    listed = client.get(f"/api/projects/{project_id}/ai-evaluations").json()
    assert len(listed) == 2
    audit = client.get(f"/api/projects/{project_id}/reports/audit-package").json()
    effectiveness = audit["metrics"]["ai_effectiveness"]
    assert effectiveness["evaluation_run_id"] == repeated["id"]
    assert effectiveness["truth_hit"]["percentage"] == 50.0
    assert effectiveness["key_omissions"]["percentage"] == 50.0
    assert effectiveness["unsupported_expansions"]["percentage"] == 50.0
    assert truth_key not in audit.__str__()


def test_evaluation_truth_is_not_accepted_as_a_normal_or_wrong_evaluation_input(client) -> None:
    project_id = create_project(client)
    input_asset_id = create_asset(client, project_id)
    truth_asset_id = create_asset(
        client, project_id, name="evaluation-truth.json", asset_type="evaluation_truth",
        purpose="独立评价 AI 输出",
    )
    run = client.post(f"/api/projects/{project_id}/ai-runs", json=run_input(input_asset_id)).json()
    wrong_asset_id = create_asset(client, project_id, name="other.txt", asset_type="other")
    payload = {
        "truth_asset_id": wrong_asset_id,
        "ai_run_ids": [run["id"]],
    }
    assert client.post(f"/api/projects/{project_id}/ai-evaluations", json=payload).status_code == 422
    assert client.post(
        f"/api/projects/{project_id}/ai-runs",
        json=run_input(truth_asset_id),
    ).status_code == 422
