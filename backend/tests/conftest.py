from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.repository import ProjectRepository


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    database_path = tmp_path / "test-design.db"
    application = create_app(database_path, local_credentials_path=tmp_path / ".env.local")
    application.state.repository = ProjectRepository(database_path)
    with TestClient(application) as test_client:
        yield test_client
