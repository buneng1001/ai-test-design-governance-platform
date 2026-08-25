from test_execution_batches_api import _batch_input, _published_task


def _create_batch(client):
    project_id, version_id, task_id = _published_task(client)
    task = client.get(f"/api/projects/{project_id}/test-tasks/{task_id}").json()
    case = task["cases"][0]
    batch = client.post(
        f"/api/projects/{project_id}/test-tasks/{task_id}/execution-batches",
        json=_batch_input(version_id, case["stable_case_id"]),
    ).json()
    return project_id, batch, case


def _result(source_record_id: str, case: dict, status: str, **extra) -> dict:
    return {
        "source_record_id": source_record_id,
        "stable_case_id": case["stable_case_id"],
        "case_revision_id": case["case_revision_id"],
        "status": status,
        "actual_result": status,
        **extra,
    }


def test_imports_all_statuses_and_is_idempotent(client) -> None:
    project_id, batch, case = _create_batch(client)
    statuses = ["passed", "execution_failed", "blocked", "not_executed", "execution_error"]
    response = client.post(
        f"/api/projects/{project_id}/execution-batches/{batch['id']}/results/import",
        json={"source_type": "manual", "results": [
            _result(f"source-{index}", case, result_status) for index, result_status in enumerate(statuses)
        ]},
    )
    assert response.status_code == 201, response.text
    assert len(response.json()["records"]) == 5
    duplicate = client.post(
        f"/api/projects/{project_id}/execution-batches/{batch['id']}/results/import",
        json={"source_type": "manual", "results": [_result("source-0", case, "passed")]},
    )
    assert duplicate.status_code == 201
    assert len(duplicate.json()["records"]) == 5


def test_unresolved_result_can_be_manually_rejected(client) -> None:
    project_id, batch, case = _create_batch(client)
    response = client.post(
        f"/api/projects/{project_id}/execution-batches/{batch['id']}/results/import",
        json={"source_type": "generic_automation", "results": [{
            "source_record_id": "ambiguous-1", "external_case_number": "unknown", "status": "passed",
        }]},
    )
    assert response.status_code == 201
    unresolved = response.json()["unresolved_records"][0]
    rejected = client.post(
        f"/api/projects/{project_id}/execution-batches/{batch['id']}/results/{unresolved['id']}/match",
        json={"decision": "rejected", "confirmer_name": "测试工程师", "reason": "来源记录无法确认归属"},
    )
    assert rejected.status_code == 201 or rejected.status_code == 200
    assert rejected.json()["unresolved_records"] == []


def test_retest_preserves_history_and_conflict_requires_human_conclusion(client) -> None:
    project_id, batch, case = _create_batch(client)
    base_url = f"/api/projects/{project_id}/execution-batches/{batch['id']}"
    first = client.post(
        f"{base_url}/results/import",
        json={"source_type": "manual", "results": [_result("manual-1", case, "execution_failed")]},
    ).json()
    first_id = first["records"][0]["id"]
    retest = client.post(
        f"{base_url}/results/import",
        json={"source_type": "manual", "results": [
            _result("manual-retest", case, "passed", retest_of_result_id=first_id),
        ]},
    )
    assert retest.status_code == 201, retest.text
    summary = retest.json()
    assert len(summary["case_summaries"][0]["history"]) == 2
    assert summary["case_summaries"][0]["initial_result"]["status"] == "execution_failed"
    assert summary["case_summaries"][0]["latest_result"]["status"] == "passed"

    conflict = client.post(
        f"{base_url}/results/import",
        json={"source_type": "generic_automation", "results": [
            _result("automation-1", case, "passed"),
        ]},
    )
    assert conflict.status_code == 201
    conflict_item = conflict.json()["conflicts"][0]
    blocked = client.post(
        f"{base_url}/conclusion",
        json={"conclusion": "passed", "rationale": "先处理冲突", "confirmer_name": "测试工程师"},
    )
    assert blocked.status_code == 409
    resolved = client.post(
        f"{base_url}/conflicts/{conflict_item['id']}/resolve",
        json={"decision": "passed", "rationale": "人工核对证据后采纳复测结果", "confirmer_name": "测试工程师"},
    )
    assert resolved.status_code == 200
    concluded = client.post(
        f"{base_url}/conclusion",
        json={"conclusion": "passed", "rationale": "复测通过且冲突已处理", "confirmer_name": "测试工程师"},
    )
    assert concluded.status_code == 200
    assert concluded.json()["conclusion"]["conclusion"] == "passed"
