# 1. 베이스가 될 파이썬 3.11 슬림 이미지 선택
FROM python:3.11-slim

# 2. uv 설치
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# 3. 컨테이너 안에서 작업할 폴더 설정
WORKDIR /app

# 4. uv 설정 파일들 복사
COPY pyproject.toml uv.lock* ./

# 5. uv를 사용하여 의존성 설치
RUN uv sync --frozen --no-dev

# 6. [수정] 필요한 파일 및 폴더만 명시적으로 복사
# 앱 실행에 필요한 파이썬 코드 복사
COPY main.py .
# 데이터 파일이 들어있는 metadata 폴더 복사
COPY metadata/ ./metadata/
# FAISS 인덱스 폴더 복사
COPY faiss_indices/ ./faiss_indices/

# 7. uv를 사용하여 앱 실행
CMD ["uv", "run", "gunicorn", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "main:app", "-b", "0.0.0.0:8000"]