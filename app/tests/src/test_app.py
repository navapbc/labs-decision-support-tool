from fastapi.testclient import TestClient

from src.app import app


def test_cors_allows_localhost_and_loopback_origins():
    client = TestClient(app)
    requested_headers = "content-type"

    for origin in ["http://localhost:5173", "http://127.0.0.1:5173"]:
        response = client.options(
            "/api/query",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": requested_headers,
            },
        )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin
        assert response.headers["access-control-allow-credentials"] == "true"
