from fastapi.testclient import TestClient

from src.chat_api import router

client = TestClient(router)


def test_api_healthcheck():
    response = client.get("/api/healthcheck")
    assert response.status_code == 200
    print(type(response))
    print(response.content)
    assert response.json()["status"] == "OK"
