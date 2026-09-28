import json
import sqlite3

from app.project_repository import ProjectRepository
from app.repository import MIGRATIONS
from test_case_generation_api import _setup as setup_case_generation


def test_migrate_applies_new_diagnostic_column_to_previous_schema(tmp_path) -> None:
    database_path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(MIGRATIONS[0])
        for version, migration in enumerate(MIGRATIONS[1:-1], start=1):
            connection.executescript(migration)
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (version, "2026-01-01T00:00:00+00:00"),
            )
        # 模拟历史版本已错误记录最新迁移编号，但实际字段没有创建。
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (len(MIGRATIONS) - 1, "2026-01-01T00:00:00+00:00"),
        )

    ProjectRepository(database_path).migrate()

    with sqlite3.connect(database_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(ai_run_attempts)")}
    assert "diagnostic" in columns


def test_migrate_removes_legacy_plaintext_model_keys(tmp_path) -> None:
    database_path = tmp_path / "legacy-model-config.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(MIGRATIONS[0])
        cleanup_version = next(
            version for version, migration in enumerate(MIGRATIONS[1:], start=1)
            if "DELETE FROM ai_model_configs" in migration
        )
        for version, migration in enumerate(MIGRATIONS[1:cleanup_version - 1], start=1):
            connection.executescript(migration)
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (version, "2026-01-01T00:00:00+00:00"),
            )
        connection.execute(
            "INSERT INTO ai_model_configs(client_id, config_json, updated_at) VALUES (?, ?, ?)",
            ("legacy", '{"api_key":"legacy-secret"}', "2026-01-01T00:00:00+00:00"),
        )

    ProjectRepository(database_path).migrate()

    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT config_json FROM ai_model_configs").fetchall() == []
        assert connection.execute("SELECT name FROM sqlite_master WHERE name = 'ai_model_connection_records'").fetchone()


def test_migrate_adds_candidate_history_to_previous_schema(tmp_path) -> None:
    database_path = tmp_path / "legacy-case-generation.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(MIGRATIONS[0])
        for version, migration in enumerate(MIGRATIONS[1:-1], start=1):
            connection.executescript(migration)
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (version, "2026-01-01T00:00:00+00:00"),
            )

    ProjectRepository(database_path).migrate()

    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'case_generation_history'"
        ).fetchone()


def test_migrate_keeps_historical_requirement_review_design_and_case_records_readable(client) -> None:
    project_id, design_id, mapping_id = setup_case_generation(client)
    generation = client.post(
        f"/api/projects/{project_id}/test-designs/{design_id}/case-generations",
        json={"template_mapping_id": mapping_id, "variants": ["normal"]},
    ).json()
    batch = client.post(f"/api/projects/{project_id}/case-generations/{generation['id']}/reviews", json={}).json()
    for suggestion in batch["suggestions"]:
        assert client.patch(
            f"/api/projects/{project_id}/case-review-batches/{batch['id']}/suggestions/{suggestion['id']}",
            json={"decision": "rejected", "reason": "历史兼容验收"},
        ).status_code == 200
    confirmed = client.post(
        f"/api/projects/{project_id}/case-review-batches/{batch['id']}/confirm",
        json={"confirmer_name": "历史兼容验收", "inclusion": {
            candidate["id"]: True for candidate in generation["candidates"]
        }},
    )
    assert confirmed.status_code == 200
    stable_case_ids = [item["stable_case_id"] for item in confirmed.json()["revisions"] if item["stable_case_id"]]
    version = client.get(f"/api/projects/{project_id}/requirement-versions").json()[0]
    analysis_id = client.get(f"/api/projects/{project_id}/workflow").json()["asset_ids"]["requirement_analysis_id"]
    before = client.get(f"/api/projects/{project_id}/requirement-reviews/{analysis_id}").json()

    # 模拟发行升级再次执行迁移；历史 JSON 资产和稳定 ID 不得被迁移覆盖或改写。
    client.app.state.repository.migrate()

    after = client.get(f"/api/projects/{project_id}/requirement-reviews/{analysis_id}").json()
    restored_generation = client.get(f"/api/projects/{project_id}/case-generations/{generation['id']}").json()
    with sqlite3.connect(client.app.state.repository.database_path) as connection:
        batch_payload = json.loads(connection.execute(
            "SELECT payload_json FROM case_review_batches WHERE id = ?", (batch["id"],)
        ).fetchone()[0])
    assert client.get(f"/api/projects/{project_id}/requirement-versions").json()[0]["id"] == version["id"]
    assert [item["stable_requirement_id"] for item in after["atomic_requirements"]] == [
        item["stable_requirement_id"] for item in before["atomic_requirements"]
    ]
    assert restored_generation["candidates"][0]["requirement_references"]
    assert [item["stable_case_id"] for item in batch_payload["revisions"] if item["stable_case_id"]] == stable_case_ids
