import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_app_startup():
    """앱이 정상적으로 시작되는지 테스트"""
    response = client.get("/docs")
    assert response.status_code == 200


def test_search_endpoint_exists():
    """검색 엔드포인트가 존재하는지 테스트"""
    response = client.post("/search", json={"query": "test"})
    # 503은 서비스가 준비되지 않았을 때, 422는 validation 에러
    # 둘 다 엔드포인트가 존재한다는 의미
    assert response.status_code in [200, 422, 503]


def test_openapi_schema():
    """OpenAPI 스키마가 정상적으로 생성되는지 테스트"""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert "openapi" in data
    assert "info" in data