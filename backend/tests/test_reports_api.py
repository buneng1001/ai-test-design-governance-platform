import base64

from test_case_generation_api import _setup


def test_reports_are_independent_downloadable_contracts_and_audit_excludes_raw_assets(client) -> None:
    project_id, design_id, mapping_id = _setup(client)
    client.post(f"/api/projects/{project_id}/assets", json={
        "name": "禁止资料", "asset_type": "other", "provenance_kind": "prohibited",
        "source": "未授权来源", "usage_permission": "prohibited", "model_permission": "denied",
        "requirement_version": "V1", "purpose": "边界测试",
        "content_base64": base64.b64encode(b"forbidden-content").decode(), "change_reason": "测试过滤",
    })
    generation = client.post(
        f"/api/projects/{project_id}/test-designs/{design_id}/case-generations",
        json={"template_mapping_id": mapping_id, "variants": ["normal"]},
    ).json()
    review = client.post(
        f"/api/projects/{project_id}/case-generations/{generation['id']}/reviews", json={}
    ).json()
    for suggestion in review["suggestions"]:
        client.patch(
            f"/api/projects/{project_id}/case-review-batches/{review['id']}/suggestions/{suggestion['id']}",
            json={"decision": "accepted", "reason": "测试工程师确认"},
        )
    confirmed = client.post(
        f"/api/projects/{project_id}/case-review-batches/{review['id']}/confirm",
        json={"confirmer_name": "测试工程师", "inclusion": {
            review["suggestions"][0]["candidate_id"]: True,
        }},
    )
    assert confirmed.status_code == 200, confirmed.text

    design_report = client.get(f"/api/projects/{project_id}/reports/test-design")
    governance_report = client.get(f"/api/projects/{project_id}/reports/execution-governance")
    audit_package = client.get(f"/api/projects/{project_id}/reports/audit-package")
    assert design_report.status_code == 200
    assert governance_report.status_code == 200
    assert audit_package.status_code == 200
    assert design_report.json()["contract_version"] == "test-design-report.v1"
    assert governance_report.json()["contract_version"] == "execution-governance-report.v1"
    audit_payload = audit_package.json()
    assert audit_payload["contract_version"] == "audit-package.v1"
    assert audit_payload["metrics"]["ai_effectiveness"]["truth_hit"]["status"] == "not_evaluated"
    assert "content_base64" not in audit_package.text
    assert "evaluation-truth" not in audit_package.text
    assert audit_payload["evidence"]["excluded_asset_count"] == 1
    assert "禁止资料" not in audit_package.text

    for report_type in ("test-design", "execution-governance", "audit-package"):
        downloaded = client.get(f"/api/projects/{project_id}/reports/{report_type}/download")
        assert downloaded.status_code == 200
        assert downloaded.headers["content-type"].startswith("application/json")
        assert "attachment" in downloaded.headers["content-disposition"]
