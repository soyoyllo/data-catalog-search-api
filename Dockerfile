FROM python:3.11-slim

WORKDIR /app

# 시스템 패키지 설치
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# uv 설치
RUN pip install uv

# uv 설정 파일 복사
COPY pyproject.toml uv.lock* ./

# CPU 전용 torch 설치
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

# uv로 의존성 설치
RUN uv sync --frozen --no-dev

# 앱 파일 복사
COPY main.py .
COPY metadata/ ./metadata/

# FAISS 인덱스 디렉토리 생성
RUN mkdir -p ./faiss_indices

# uv로 앱 실행
CMD ["uv", "run", "python", "main.py"]