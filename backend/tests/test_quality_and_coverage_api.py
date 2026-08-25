from test_case_generation_api import _setup


def _confirmed_design(client) -> tuple[int, int, int, dict]:
    project_id, design_id, mapping_id = _setup(client)
    generation = client.post(
        f"/api/projects/{project_id}/test-designs/{design_id}/case-generations",
        json={"template_mapping_id": mapping_id, "variants": ["normal"]},
    ).json()
    review_batch = client.post(
        f"/api/projects/{project_id}/case-generations/{generation['id']}/reviews", json={}
    ).json()
    for suggestion in review_batch["suggestions"]:
        client.patch(
            f"/api/projects/{project_id}/case-review-batches/{review_batch['id']}"
            f"/suggestions/{suggestion['id']}",
            json={"decision": "accepted", "reason": "测试工程师确认建议"},
        )
    confirmed = client.post(
        f"/api/projects/{project_id}/case-review-batches/{review_batch['id']}/confirm",
        json={
            "confirmer_name": "测试工程师",
            "inclusion": {review_batch["suggestions"][0]["candidate_id"]: True},
        },
    ).json()
    version_id = client.get(f"/api/projects/{project_id}/requirement-versions").json()[0]["id"]
    return project_id, version_id, design_id, confirmed


def test_quality_issue_pattern_requires_confirmation_and_links_execution_evidence(client) -> None:
    project_id, version_id, design_id, review_batch = _confirmed_design(client)
    case = review_batch["revisions"][0]
    task = client.post(
        f"/api/projects/{project_id}/case-review-batches/{review_batch['id']}/test-tasks",
        json={"confirmer_name": "测试工程师", "execution_target": "manual",
              "stable_case_ids": [case["stable_case_id"]]},
    ).json()
    batch = client.post(
        f"/api/projects/{project_id}/test-tasks/{task['task_id']}/execution-batches",
        json={"product_version": "1.0", "requirement_version_id": version_id, "environment": "演示环境",
              "scope": "冒烟", "responsible_person": "测试工程师",
              "stable_case_ids": [case["stable_case_id"]]},
    ).json()
    result_url = f"/api/projects/{project_id}/execution-batches/{batch['id']}/results/import"
    imported = client.post(result_url, json={
        "source_type": "manual", "results": [
            {"source_record_id": "manual-1", "stable_case_id": case["stable_case_id"],
             "case_revision_id": case["id"], "status": "execution_failed",
             "evidence_references": ["evidence://failure/1"]},
        ],
    }).json()
    result_id = imported["records"][0]["id"]
    issue_payload = {
        "execution_result_id": result_id, "phenomenon": "保存状态后页面显示旧状态",
        "evidence_references": ["evidence://failure/1"], "severity": "high",
        "problem_pattern": "状态保存后展示不一致", "release_impact": "blocks_release",
    }
    issue = client.post(f"/api/projects/{project_id}/quality-issues", json=issue_payload)
    assert issue.status_code == 201, issue.text
    invalid_retest = client.post(f"/api/projects/{project_id}/quality-issues", json={
        **issue_payload, "retest_result_id": result_id,
    })
    assert invalid_retest.status_code == 422
    second = client.post(f"/api/projects/{project_id}/quality-issues", json={
        **issue_payload, "phenomenon": "重复进入页面后状态仍未刷新", "execution_result_id": result_id,
    })
    assert second.status_code == 201
    pattern = client.post(f"/api/projects/{project_id}/defect-patterns/suggestions", json={
        "quality_issue_ids": [issue.json()["id"], second.json()["id"]],
    })
    assert pattern.status_code == 201
    assert pattern.json()["status"] == "pending_confirmation"
    assert pattern.json()["root_cause_claim"] == "not_established"
    confirmed = client.post(
        f"/api/projects/{project_id}/defect-patterns/{pattern.json()['id']}/confirm",
        json={"confirmer_name": "测试工程师"},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"


def test_coverage_exposes_denominators_gaps_and_ignores_unresolved_result(client) -> None:
    project_id, version_id, design_id, review_batch = _confirmed_design(client)
    case = review_batch["revisions"][0]
    task = client.post(
        f"/api/projects/{project_id}/case-review-batches/{review_batch['id']}/test-tasks",
        json={"confirmer_name": "测试工程师", "execution_target": "manual",
              "stable_case_ids": [case["stable_case_id"]]},
    ).json()
    batch = client.post(
        f"/api/projects/{project_id}/test-tasks/{task['task_id']}/execution-batches",
        json={"product_version": "1.0", "requirement_version_id": version_id, "environment": "演示环境",
              "scope": "冒烟", "responsible_person": "测试工程师",
              "stable_case_ids": [case["stable_case_id"]]},
    ).json()
    coverage_url = (
        f"/api/projects/{project_id}/coverage?requirement_version_id={version_id}&design_id={design_id}"
        f"&case_review_batch_id={review_batch['id']}&execution_batch_id={batch['id']}"
    )
    before = client.get(coverage_url)
    assert before.status_code == 200, before.text
    metrics = before.json()["metrics"]
    assert metrics["requirement_coverage"]["numerator"] >= 1
    assert set(metrics) == {
        "requirement_coverage", "risk_coverage", "dimension_coverage",
        "execution_coverage", "automation_coverage",
    }
    unresolved = client.post(
        f"/api/projects/{project_id}/execution-batches/{batch['id']}/results/import",
        json={"source_type": "generic_automation", "results": [{
            "source_record_id": "unknown", "status": "passed", "external_case_number": "unknown",
        }]},
    )
    assert unresolved.status_code == 201
    after = client.get(coverage_url).json()["metrics"]["execution_coverage"]
    assert after["numerator"] == 0
    assert len(after["uncovered_items"]) == 1
    matched = client.post(
        f"/api/projects/{project_id}/execution-batches/{batch['id']}/results/import",
        json={"source_type": "manual", "results": [{
            "source_record_id": "matched-manual", "stable_case_id": case["stable_case_id"],
            "case_revision_id": case["id"], "status": "passed",
        }]},
    )
    assert matched.status_code == 201
    conflict = client.post(
        f"/api/projects/{project_id}/execution-batches/{batch['id']}/results/import",
        json={"source_type": "generic_automation", "results": [{
            "source_record_id": "matched-automation", "stable_case_id": case["stable_case_id"],
            "case_revision_id": case["id"], "status": "execution_failed",
        }]},
    )
    assert conflict.status_code == 201
    assert client.get(coverage_url).json()["metrics"]["execution_coverage"]["numerator"] == 0
    invalid_relation = client.get(coverage_url.replace(f"design_id={design_id}", f"design_id={design_id + 100}"))
    assert invalid_relation.status_code == 404
