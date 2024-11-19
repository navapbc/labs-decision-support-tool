
import json
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.chat_api import app
# from src.healthcheck import healthcheck_router

# app = FastAPI()
client = TestClient(app)


def test_api_healthcheck():
    response = client.get("/api_healthcheck")
    assert response.status_code == 200
    # response_data = json.loads(response.content)
    print(response.content)
    # assert response.json() == {"msg": "Hello World"}

