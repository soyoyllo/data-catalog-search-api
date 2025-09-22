# Data Catalog Search API

FastAPI 기반의 데이터 카탈로그 검색 서비스로, 벡터 유사도 검색을 통해 메타데이터를 검색할 수 있습니다.

## 🚀 주요 기능

- **벡터 유사도 검색**: FAISS와 Sentence Transformers를 사용한 고성능 검색
- **RESTful API**: FastAPI 기반의 자동 문서화된 API
- **메타데이터 관리**: 테이블 및 컬럼 정보의 체계적 관리
- **Docker 지원**: 컨테이너화된 배포 환경
- **uv 패키지 관리**: 빠르고 현대적인 Python 패키지 관리

## 🛠️ 기술 스택

- **Python 3.11+**
- **FastAPI**: 웹 프레임워크
- **uv**: 빠르고 현대적인 Python 패키지 관리자
- **FAISS**: 벡터 검색 엔진
- **Sentence Transformers**: 임베딩 모델
- **Docker**: 컨테이너화

## 📋 사전 요구사항

- Python 3.11 이상
- [uv](https://github.com/astral-sh/uv) (권장)
- Docker (선택사항)

## 🚀 빠른 시작

### 1. 저장소 클론

```bash
git clone <repository-url>
cd data-catalog-search-api
```

### 2. uv 설치

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# 또는 pip로 설치
pip install uv
```

### 3. 의존성 설치

```bash
uv sync
```

### 4. 서버 실행

```bash
# 개발 모드
uv run python main.py

# 또는 직접 실행
python main.py
```

### 5. API 문서 확인

브라우저에서 `http://localhost:8000/docs`에 접속하여 Swagger UI를 확인할 수 있습니다.

## 🐳 Docker 사용

### Docker Compose로 실행

```bash
# 서비스 시작
docker-compose up -d

# 로그 확인
docker-compose logs -f

# 서비스 중지
docker-compose down
```

### Docker로 직접 실행

```bash
# 이미지 빌드
docker build -t data-catalog-search-api .

# 컨테이너 실행
docker run -p 8000:8000 data-catalog-search-api
```

## 📡 API 사용법

### 검색 요청

```bash
curl -X POST "http://localhost:8000/search" \
     -H "Content-Type: application/json" \
     -d '{"query": "사용자 정보 테이블"}'
```

### 응답 예시

```json
{
  "status": "success",
  "original_query": "사용자 정보 테이블",
  "llm_response": "LLM 응답은 향후 추가될 예정입니다.",
  "results": [
    {
      "similarity_score": 0.95,
      "table_name": "users",
      "table_description": "사용자 기본 정보를 저장하는 테이블",
      "openmetadata_url": "https://example.com/table/users",
      "column_descriptions": [
        {
          "column_name": "id",
          "description": "사용자 고유 식별자",
          "data_type": "INTEGER",
          "is_primary_key": true
        }
      ]
    }
  ]
}
```

## 📁 프로젝트 구조

```
data-catalog-search-api/
├── main.py                 # FastAPI 애플리케이션
├── pyproject.toml         # uv 프로젝트 설정
├── uv.lock               # 의존성 버전 고정
├── Dockerfile            # Docker 이미지 빌드
├── docker-compose.yml    # Docker Compose 설정
├── metadata/             # 메타데이터 파일들
│   └── enriched_metadata_clustered.json
└── README.md
```

## 🔧 개발

### 의존성 관리

```bash
# 새 패키지 추가
uv add package-name

# 개발 의존성 추가
uv add --dev package-name

# 의존성 업데이트
uv sync
```

### 코드 포맷팅

```bash
# Black으로 포맷팅
uv run black .

# isort로 import 정렬
uv run isort .
```

## 🚀 배포

### VPN 서버 배포

1. VPN 연결
2. 서버에 접속
3. 프로젝트 디렉토리로 이동
4. Docker Compose로 배포

```bash
# 서버에서 실행
git pull origin main
docker-compose down
docker-compose up -d --build
```