from fastapi.testclient import TestClient

from app.main import app


def test_live():
    response = TestClient(app).get("/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
