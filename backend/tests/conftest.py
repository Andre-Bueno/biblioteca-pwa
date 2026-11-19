import os

# Test-only secret; set before app modules read settings.
os.environ.setdefault("SECRET_KEY", "test-only-secret-key-not-for-production-0123456789")

import pytest  # noqa: E402
from app.main import create_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())
