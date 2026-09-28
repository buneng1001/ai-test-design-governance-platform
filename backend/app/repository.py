import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

MIGRATIONS = (
    """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        test_object TEXT NOT NULL,
        description TEXT NOT NULL,
        settings_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS assets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id),
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS asset_provenance_revisions (
        asset_id INTEGER NOT NULL REFERENCES assets(id),
        revision INTEGER NOT NULL,
        name TEXT NOT NULL,
        asset_type TEXT NOT NULL,
        provenance_kind TEXT NOT NULL,
        source TEXT NOT NULL,
        usage_permission TEXT NOT NULL,
        model_permission TEXT NOT NULL,
        requirement_version TEXT NOT NULL,
        purpose TEXT NOT NULL,
        sha256 TEXT NOT NULL,
        change_reason TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (asset_id, revision)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS requirement_packages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id),
        name TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        published_version_id INTEGER,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS requirement_versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id),
        package_id INTEGER NOT NULL REFERENCES requirement_packages(id),
        version INTEGER NOT NULL,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(project_id, version),
        UNIQUE(package_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id),
        task_type TEXT NOT NULL,
        model_config_json TEXT NOT NULL,
        prompt_version TEXT NOT NULL,
        input_asset_versions_json TEXT NOT NULL,
        output_json TEXT,
        validation_status TEXT NOT NULL,
        validation_errors_json TEXT NOT NULL,
        status TEXT NOT NULL,
        is_mock INTEGER NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS ai_run_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL REFERENCES ai_runs(id),
        attempt INTEGER NOT NULL,
        started_at TEXT NOT NULL,
        elapsed_ms INTEGER NOT NULL,
        status TEXT NOT NULL,
        error_code TEXT,
        retryable INTEGER NOT NULL,
        UNIQUE(run_id, attempt)
    );
    CREATE TABLE IF NOT EXISTS ai_run_dispositions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL REFERENCES ai_runs(id),
        decision TEXT NOT NULL,
        reason TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS requirement_analyses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id),
        requirement_version_id INTEGER NOT NULL REFERENCES requirement_versions(id),
        payload_json TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS requirement_analysis_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        analysis_id INTEGER NOT NULL REFERENCES requirement_analyses(id),
        event_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS test_designs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id),
        requirement_version_id INTEGER NOT NULL REFERENCES requirement_versions(id),
        payload_json TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS test_design_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        design_id INTEGER NOT NULL REFERENCES test_designs(id),
        event_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS template_mappings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id),
        version INTEGER NOT NULL,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(project_id, version)
    );
    CREATE TABLE IF NOT EXISTS template_mapping_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mapping_id INTEGER NOT NULL REFERENCES template_mappings(id),
        event_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS case_generations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id),
        design_id INTEGER NOT NULL REFERENCES test_designs(id),
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS case_review_batches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id),
        generation_id INTEGER NOT NULL REFERENCES case_generations(id),
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS case_review_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id INTEGER NOT NULL REFERENCES case_review_batches(id),
        event_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS test_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id),
        batch_id INTEGER NOT NULL REFERENCES case_review_batches(id),
        task_id TEXT NOT NULL,
        task_version INTEGER NOT NULL,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(task_id, task_version)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS execution_batches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id),
        test_task_id TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS execution_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id),
        stable_case_id TEXT NOT NULL,
        execution_sequence INTEGER NOT NULL,
        UNIQUE(project_id, stable_case_id, execution_sequence)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS execution_result_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id),
        batch_id INTEGER NOT NULL REFERENCES execution_batches(id),
        source_type TEXT NOT NULL,
        source_record_id TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        match_status TEXT NOT NULL,
        stable_case_id TEXT,
        case_revision_id TEXT,
        execution_sequence INTEGER,
        retest_of_result_id INTEGER REFERENCES execution_result_records(id),
        created_at TEXT NOT NULL,
        UNIQUE(batch_id, source_type, source_record_id)
    );
    CREATE TABLE IF NOT EXISTS execution_result_conflicts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id),
        batch_id INTEGER NOT NULL REFERENCES execution_batches(id),
        result_ids_json TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        resolved_at TEXT
    );
    CREATE TABLE IF NOT EXISTS execution_batch_conclusions (
        batch_id INTEGER PRIMARY KEY REFERENCES execution_batches(id),
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
    """
    ALTER TABLE execution_result_records ADD COLUMN match_reason TEXT;
    ALTER TABLE execution_result_records ADD COLUMN matched_by TEXT;
    """,
    """
    CREATE TABLE IF NOT EXISTS quality_issue_references (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id),
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS defect_patterns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id),
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS change_impact_analyses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id),
        base_version_id INTEGER NOT NULL REFERENCES requirement_versions(id),
        target_version_id INTEGER NOT NULL REFERENCES requirement_versions(id),
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS change_impact_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        analysis_id INTEGER NOT NULL REFERENCES change_impact_analyses(id),
        event_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS regression_selections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id),
        analysis_id INTEGER NOT NULL REFERENCES change_impact_analyses(id),
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_evaluation_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id),
        truth_asset_id INTEGER NOT NULL REFERENCES assets(id),
        truth_sha256 TEXT NOT NULL,
        ai_run_ids_json TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
    """
    ALTER TABLE asset_provenance_revisions ADD COLUMN content_base64 TEXT NOT NULL DEFAULT '';
    """,
    """
    ALTER TABLE projects ADD COLUMN software_version TEXT NOT NULL DEFAULT '未填写';
    """,
    """
    ALTER TABLE asset_provenance_revisions ADD COLUMN size_bytes INTEGER NOT NULL DEFAULT 0;
    """,
    """
    ALTER TABLE asset_provenance_revisions ADD COLUMN media_type TEXT NOT NULL DEFAULT 'application/octet-stream';
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_model_configs (
        client_id TEXT PRIMARY KEY,
        config_json TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
    """
    ALTER TABLE ai_run_attempts ADD COLUMN diagnostic TEXT;
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_model_connection_records (
        client_id TEXT NOT NULL,
        provider TEXT NOT NULL,
        base_url TEXT NOT NULL,
        model TEXT NOT NULL,
        status TEXT NOT NULL,
        credential_source TEXT NOT NULL,
        validated_at TEXT,
        error_type TEXT,
        detail TEXT,
        PRIMARY KEY (client_id, provider)
    );
    CREATE TABLE IF NOT EXISTS ai_model_discoveries (
        client_id TEXT NOT NULL,
        provider TEXT NOT NULL,
        base_url TEXT NOT NULL,
        models_json TEXT NOT NULL,
        discovered_at TEXT NOT NULL,
        PRIMARY KEY (client_id, provider, base_url)
    );
    DELETE FROM ai_model_configs;
    """,
    """
    CREATE TABLE IF NOT EXISTS case_generation_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        generation_id INTEGER NOT NULL REFERENCES case_generations(id),
        event_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
    """
    ALTER TABLE ai_runs ADD COLUMN source TEXT NOT NULL DEFAULT 'mock';
    ALTER TABLE ai_runs ADD COLUMN stage TEXT NOT NULL DEFAULT 'model_call';
    ALTER TABLE ai_runs ADD COLUMN batch_number INTEGER NOT NULL DEFAULT 1;
    ALTER TABLE ai_runs ADD COLUMN batch_total INTEGER NOT NULL DEFAULT 1;
    ALTER TABLE ai_runs ADD COLUMN completed_count INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE ai_runs ADD COLUMN total_count INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE ai_runs ADD COLUMN estimated_remaining_ms INTEGER;
    ALTER TABLE ai_runs ADD COLUMN recovery_point TEXT;
    ALTER TABLE ai_run_attempts ADD COLUMN error_category TEXT;
    ALTER TABLE ai_run_attempts ADD COLUMN retry_after_ms INTEGER;
    ALTER TABLE ai_run_attempts ADD COLUMN recovery_point TEXT;
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_run_controls (
        id TEXT PRIMARY KEY,
        project_id INTEGER NOT NULL,
        workflow TEXT NOT NULL,
        input_fingerprint TEXT NOT NULL,
        status TEXT NOT NULL,
        next_batch INTEGER NOT NULL,
        batch_total INTEGER NOT NULL,
        completed_count INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS ai_run_batch_results (
        run_id TEXT NOT NULL REFERENCES ai_run_controls(id),
        batch_number INTEGER NOT NULL,
        output_json TEXT NOT NULL,
        ai_run_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (run_id, batch_number),
        UNIQUE (run_id, ai_run_id)
    );
    """,
    """
    ALTER TABLE ai_run_controls ADD COLUMN payload_json TEXT NOT NULL DEFAULT '{}';
    ALTER TABLE ai_run_controls ADD COLUMN final_asset_type TEXT;
    ALTER TABLE ai_run_controls ADD COLUMN final_asset_id INTEGER;
    CREATE UNIQUE INDEX IF NOT EXISTS ai_run_controls_final_asset_unique
    ON ai_run_controls(final_asset_type, final_asset_id)
    WHERE final_asset_id IS NOT NULL;
    """,
    """
    ALTER TABLE requirement_analyses ADD COLUMN run_control_id TEXT;
    CREATE UNIQUE INDEX IF NOT EXISTS requirement_analyses_run_control_unique
    ON requirement_analyses(run_control_id) WHERE run_control_id IS NOT NULL;
    ALTER TABLE case_generations ADD COLUMN run_control_id TEXT;
    CREATE UNIQUE INDEX IF NOT EXISTS case_generations_run_control_unique
    ON case_generations(run_control_id) WHERE run_control_id IS NOT NULL;
    """,
    """
    ALTER TABLE ai_run_controls ADD COLUMN active_batch_number INTEGER;
    ALTER TABLE ai_run_controls ADD COLUMN active_lease_id TEXT;
    """,
)


# 兼容历史导入路径，项目仓储实现已按领域独立归位。
from app.project_repository import ProjectRepository
