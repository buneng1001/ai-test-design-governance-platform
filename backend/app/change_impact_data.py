from app.case_review_repository import CaseReviewRepository
from app.case_review_schemas import CaseReviewBatch
from app.design_repository import DesignRepository
from app.design_schemas import DesignAsset
from app.execution_batch_repository import ExecutionBatchRepository
from app.execution_batch_schemas import ExecutionBatch


def designs_for_project(repository: DesignRepository, project_id: int) -> list[DesignAsset]:
    with repository.connect() as connection:
        rows = connection.execute(
            "SELECT payload_json FROM test_designs WHERE project_id = ? ORDER BY id", (project_id,)
        ).fetchall()
    return [DesignAsset.model_validate_json(row["payload_json"]) for row in rows]


def case_reviews_for_project(repository: CaseReviewRepository, project_id: int) -> list[CaseReviewBatch]:
    with repository.connect() as connection:
        rows = connection.execute(
            "SELECT payload_json FROM case_review_batches WHERE project_id = ? ORDER BY id", (project_id,)
        ).fetchall()
    return [CaseReviewBatch.model_validate_json(row["payload_json"]) for row in rows]


def batches_for_project(repository: ExecutionBatchRepository, project_id: int) -> list[ExecutionBatch]:
    with repository.connect() as connection:
        rows = connection.execute(
            "SELECT payload_json FROM execution_batches WHERE project_id = ? ORDER BY id", (project_id,)
        ).fetchall()
    return [ExecutionBatch.model_validate_json(row["payload_json"]) for row in rows]
