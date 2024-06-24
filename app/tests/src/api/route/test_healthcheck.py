import json
import logging
import pytest

from fastapi.testclient import TestClient

from healthcheck import app


@pytest.fixture(name="test_client")
def fixture_test_client():
    return TestClient(app)


class TestAPI:
    def test_read_healthcheck(self, caplog, test_client):
        with caplog.at_level(logging.INFO, logger="chatbot.chatbot_api"):
            response = test_client.get("/healthcheck")
            response_data = json.loads(response.content)
            assert response.status_code == 200
            assert response_data["status"] == "OK"
            assert "Healthy" in caplog.messages[1]
