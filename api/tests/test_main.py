import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_health_check():
    """헬스 체크 엔드포인트 테스트"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_search_endpoint():
    """검색 엔드포인트 기본 테스트"""
    response = client.post(
        "/search",
        json={"query": "사용자 테이블"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "original_query" in data
    assert data["original_query"] == "사용자 테이블"


def test_search_empty_query():
    """빈 쿼리로 검색 테스트"""
    response = client.post(
        "/search",
        json={"query": ""}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"


def test_search_invalid_json():
    """잘못된 JSON 요청 테스트"""
    response = client.post(
        "/search",
        json={"invalid": "data"}
    )
    # FastAPI가 자동으로 validation을 수행하므로 422 에러가 발생할 수 있음
    assert response.status_code in [200, 422]


@pytest.mark.asyncio
async def test_search_async():
    """비동기 검색 함수 테스트"""
    from main import search_metadata
    from main import QueryRequest
    
    request = QueryRequest(query="테스트 쿼리")
    response = await search_metadata(request)
    
    assert response.status == "success"
    assert response.original_query == "테스트 쿼리"


def test_api_docs():
    """API 문서 엔드포인트 테스트"""
    response = client.get("/docs")
    assert response.status_code == 200


def test_openapi_schema():
    """OpenAPI 스키마 엔드포인트 테스트"""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert "openapi" in data
    assert "info" in data
