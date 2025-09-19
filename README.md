# Data Catalog Search API

FastAPI 기반의 데이터 카탈로그 검색 서비스로, 벡터 유사도 검색을 통해 메타데이터를 검색할 수 있습니다.

## 🚀 주요 기능

- **벡터 유사도 검색**: FAISS와 Sentence Transformers를 사용한 고성능 검색
- **RESTful API**: FastAPI 기반의 자동 문서화된 API
- **메타데이터 관리**: 테이블 및 컬럼 정보의 체계적 관리
- **Docker 지원**: 컨테이너화된 배포 환경
- **CI/CD**: GitHub Actions를 통한 자동화된 린팅, 테스트 및 배포
- **uv 패키지 관리**: 빠르고 현대적인 Python 패키지 관리

## 🛠️ 기술 스택

- **Python 3.11+**
- **FastAPI**: 웹 프레임워크
- **uv**: 빠르고 현대적인 Python 패키지 관리자
- **FAISS**: 벡터 검색 엔진
- **Sentence Transformers**: 임베딩 모델
- **LangChain**: LLM 통합 프레임워크
- **Docker**: 컨테이너화
- **GitHub Actions**: CI/CD
- **pytest**: 간단한 테스트 프레임워크

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
# 개발 의존성 포함 설치
uv sync --dev

# 또는 Makefile 사용
make install
```

### 4. 개발 서버 실행

```bash
# uv 사용
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 또는 Makefile 사용
make dev
```

### 5. API 문서 확인

브라우저에서 `http://localhost:8000/docs`에 접속하여 Swagger UI를 확인할 수 있습니다.

## 🐳 Docker 사용

### Docker Compose로 실행

```bash
# 서비스 시작
docker-compose up -d

# 로그 확인
make logs

# 서비스 중지
make down
```

### Docker 이미지 직접 빌드

```bash
docker build -t data-catalog-search-api .
docker run -p 8000:8000 data-catalog-search-api
```

## 🧪 개발 및 테스트

### 코드 포맷팅

```bash
# 코드 포맷팅
make format

# 린팅 검사
make lint
```

### 테스트 실행

```bash
# 간단한 테스트 실행
make test
```


### 캐시 정리

```bash
make clean
```

## 📁 프로젝트 구조

```
data-catalog-search-api/
├── .github/
│   └── workflows/
│       └── ci.yml              # GitHub Actions CI/CD
├── tests/
│   ├── __init__.py
│   └── test_main.py            # 간단한 테스트
├── metadata/                   # 메타데이터 파일들
│   └── enriched_metadata_clustered.json
├── faiss_indices/             # FAISS 인덱스 파일들
│   └── faiss_index_e5_small/
├── faiss_index_e5_small/      # FAISS 인덱스 (기존)
├── main.py                    # FastAPI 애플리케이션
├── pyproject.toml             # uv 프로젝트 설정
├── uv.lock                    # 의존성 잠금 파일
├── requirements.txt           # pip 호환성용 (레거시)
├── Dockerfile                 # Docker 설정
├── docker-compose.yml         # Docker Compose 설정
├── Makefile                   # 개발 명령어
├── README.md                  # 프로젝트 문서
└── .gitignore                 # Git 무시 파일
```

## 🔧 환경 변수

다음 환경 변수들을 설정할 수 있습니다:

- `OPENMETADATA_BASE_URL`: OpenMetadata 기본 URL (기본값: https://de4f5334deb3.ngrok-free.app/)

## 📊 API 엔드포인트

### POST /search

데이터 카탈로그를 검색합니다.

**요청:**
```json
{
  "query": "사용자 검색 쿼리"
}
```

**응답:**
```json
{
  "status": "success",
  "original_query": "사용자 검색 쿼리",
  "results": [
    {
      "similarity_score": 0.95,
      "table_name": "TABLE_NAME",
      "table_description": "테이블 설명",
      "openmetadata_url": "https://...",
      "column_descriptions": [
        {
          "column_name": "COLUMN_NAME",
          "description": "컬럼 설명",
          "data_type": "VARCHAR",
          "is_primary_key": false
        }
      ]
    }
  ]
}
```

## 🚀 CI/CD

이 프로젝트는 GitHub Actions를 사용하여 자동화된 CI/CD 파이프라인을 제공합니다:

- **테스트**: 간단한 pytest 테스트 실행 (앱 시작, 엔드포인트 존재 확인, OpenAPI 스키마 검증)
- **린팅**: Black, isort, flake8, mypy 검사
- **보안 스캔**: Safety, Bandit을 사용한 보안 검사
- **Docker 빌드**: 자동 Docker 이미지 빌드 및 GitHub Container Registry 푸시
- **배포**: 스테이징/프로덕션 환경 자동 배포

## 🤝 기여하기

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Install dependencies (`make install`)
4. Make your changes
5. Run tests and linting (`make test && make lint`)
6. Commit your changes (`git commit -m 'Add some amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## 📝 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.

## 📞 지원

문제가 발생하거나 질문이 있으시면 이슈를 생성해 주세요.

---
# Test
