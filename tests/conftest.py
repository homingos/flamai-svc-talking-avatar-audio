# /tests/conftest.py

import pytest
from fastapi.testclient import TestClient
import os


os.environ["MINIMAX_API_KEY"] = "test-key"
os.environ["MINIMAX_GROUP_ID"] = "test-group"

from app import app

@pytest.fixture(scope="module")
def test_client():
    """Create a TestClient instance for testing the API."""
    # The TestClient will correctly run the app's lifespan,
    # and the MinimaxTtsService will now initialize successfully.
    with TestClient(app) as client:
        yield client