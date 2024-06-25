import json
import logging

import pytest
from fastapi.testclient import TestClient

from src.healthcheck import healthcheck_router


@pytest.fixture(name="test_client")
def fixture_test_client():
    return TestClient(healthcheck_router)


class TestAPI:
    def test_get_healthcheck_200(self, caplog, test_client):
        with caplog.at_level(logging.INFO, logger="chatbot.healthcheck"):
            response = test_client.get("/health")
            response_data = json.loads(response.content)
            assert response.status_code == 200
            assert response_data["status"] == "OK"
            assert "Healthy" in caplog.messages[1]
