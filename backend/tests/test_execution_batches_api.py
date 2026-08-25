import csv
import io
from concurrent.futures import ThreadPoolExecutor

from test_test_tasks_api import _confirmed_batch


def _published_task(client) -> tuple[int, int, int]:
    project_id, review_batch = _confirmed_batch(client)
    case_id = review_batch["revisions"][0]["stable_case_id"]
    task = client.post(
        f"/api/projects/{project_id}/case-review-batches/{review_batch['id']}/test-tasks",
        json={
            "confirmer_name": "测试工程师",
            "execution_target": "manual",
            "stable_case_ids": [case_id],
        },
    ).json()
    version_id = client.get(f"/api/projects/{project_id}/requirement-versions").json()[0]["id"]
    return project_id, version_id, task["task_id"]


def _batch_input(version_id: int, case_id: str, *, scope: str = "冒烟范围") -> dict:
    return {
        "product_version": "采集设备 1.0.0",
        "requirement_version_id": version_id,
        "environment": "离线演示环境",
        "scope": scope,
        "responsible_person": "测试工程师",
        "stable_case_ids": [case_id],
    }


def test_execution_batch_freezes_task_context_and_downloads_manual_file(client) -> None:
    project_id, version_id, task_id = _published_task(client)
    task = client.get(f"/api/projects/{project_id}/test-tasks/{task_id}").json()
    case = task["cases"][0]
    response = client.post(
        f"/api/projects/{project_id}/test-tasks/{task_id}/execution-batches",
        json=_batch_input(version_id, case["stable_case_id"]),
    )
    assert response.status_code == 201
    batch = response.json()
    assert batch["product_version"] == "采集设备 1.0.0"
    assert batch["execution_target"] == "manual"
    assert batch["cases"][0]["case_revision_id"] == case["case_revision_id"]
    assert batch["cases"][0]["display_number"].endswith("-1")

    changed = client.patch(
        f"/api/projects/{project_id}/case-review-batches/{task['case_review_batch_id']}"
        f"/cases/{case['stable_case_id']}/status",
        json={
            "participation_status": "pending_retest",
            "reason": "发现需要复测",
            "confirmer_name": "测试工程师",
        },
    )
    assert changed.status_code == 200
    frozen = client.get(f"/api/projects/{project_id}/execution-batches/{batch['id']}").json()
    assert frozen["cases"][0]["execution_sequence"] == 1
    assert frozen["cases"][0]["case_revision_id"] == case["case_revision_id"]
    assert frozen["cases"][0]["participation_status"] == "included"

    downloaded = client.get(
        f"/api/projects/{project_id}/execution-batches/{batch['id']}/manual-file"
    )
    rows = list(csv.DictReader(io.StringIO(downloaded.content.decode("utf-8-sig"))))
    assert downloaded.status_code == 200
    assert rows[0]["filling_status"] == "未填写"
    assert rows[0]["execution_record_id"] == f"batch-{batch['id']}-seq-1"
    assert rows[0]["evidence_references"] == ""


def test_execution_batch_repeated_creation_allocates_new_sequence_without_overwrite(client) -> None:
    project_id, version_id, task_id = _published_task(client)
    case_id = client.get(f"/api/projects/{project_id}/test-tasks/{task_id}").json()["cases"][0]["stable_case_id"]
    first = client.post(
        f"/api/projects/{project_id}/test-tasks/{task_id}/execution-batches",
        json=_batch_input(version_id, case_id),
    ).json()
    second = client.post(
        f"/api/projects/{project_id}/test-tasks/{task_id}/execution-batches",
        json=_batch_input(version_id, case_id, scope="回归范围"),
    ).json()
    assert first["cases"][0]["execution_sequence"] == 1
    assert second["cases"][0]["execution_sequence"] == 2
    assert client.get(f"/api/projects/{project_id}/execution-batches/{first['id']}").json()["scope"] == "冒烟范围"


def test_execution_batch_concurrent_creation_allocates_distinct_sequences(client) -> None:
    project_id, version_id, task_id = _published_task(client)
    case_id = client.get(f"/api/projects/{project_id}/test-tasks/{task_id}").json()["cases"][0]["stable_case_id"]

    def create_batch(index: int):
        return client.post(
            f"/api/projects/{project_id}/test-tasks/{task_id}/execution-batches",
            json=_batch_input(version_id, case_id, scope=f"并发范围 {index}"),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(create_batch, range(2)))

    assert [response.status_code for response in responses] == [201, 201]
    sequences = {response.json()["cases"][0]["execution_sequence"] for response in responses}
    assert sequences == {1, 2}


def test_execution_batch_rejects_empty_or_inconsistent_scope(client) -> None:
    project_id, version_id, task_id = _published_task(client)
    task = client.get(f"/api/projects/{project_id}/test-tasks/{task_id}").json()
    base = _batch_input(version_id, task["cases"][0]["stable_case_id"])
    empty = client.post(
        f"/api/projects/{project_id}/test-tasks/{task_id}/execution-batches",
        json={**base, "stable_case_ids": []},
    )
    inconsistent = client.post(
        f"/api/projects/{project_id}/test-tasks/{task_id}/execution-batches",
        json={**base, "requirement_version_id": version_id + 1},
    )
    assert empty.status_code == 422
    assert inconsistent.status_code == 409
