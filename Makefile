# Makefile

# uv를 사용한 개발 환경 설정
.PHONY: install dev test lint format clean

# 개발 의존성 설치
install:
	@echo "▶ uv를 사용하여 의존성을 설치합니다..."
	uv sync --dev

# 개발 서버 실행
dev:
	@echo "▶ 개발 서버를 실행합니다..."
	uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 간단한 테스트 실행
test:
	@echo "▶ 간단한 테스트를 실행합니다..."
	uv run pytest -v

# 린팅 실행
lint:
	@echo "▶ 코드 린팅을 실행합니다..."
	uv run black --check .
	uv run isort --check-only .
	uv run flake8 .
	uv run mypy .

# 코드 포맷팅
format:
	@echo "▶ 코드를 포맷팅합니다..."
	uv run black .
	uv run isort .

# 캐시 및 임시 파일 정리
clean:
	@echo "▶ 캐시 및 임시 파일을 정리합니다..."
	rm -rf .mypy_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

# 업데이트 및 배포를 위한 기본 명령어
deploy:
	@echo "▶ 최신 코드를 가져옵니다 (git pull)..."
	@git pull origin main
	@echo "▶ Docker 이미지를 새로 빌드하고 재시작합니다..."
	@docker-compose up -d --build
	@echo "✅ 배포 완료!"

# 컨테이너 상태 확인
status:
	@docker-compose ps

# 실시간 로그 확인
logs:
	@echo "▶ API 서버의 실시간 로그를 확인합니다... (종료: Ctrl + C)"
	@docker-compose logs -f metadata-search-api

# 모든 서비스 중지
down:
	@docker-compose down