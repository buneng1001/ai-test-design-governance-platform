import sqlite3

from app.project_repository import ProjectRepository
from app.repository import MIGRATIONS


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
