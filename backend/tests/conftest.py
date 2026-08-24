from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    database_path = tmp_path / "test-design.db"
    with TestClient(create_app(database_path)) as test_client:
        yield test_client

