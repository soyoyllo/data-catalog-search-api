import asyncio
import json
import logging
import os
import threading
from contextlib import asynccontextmanager, suppress
from typing import List, Dict, Optional, Any
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from langgraph_sdk import get_client
from langgraph_sdk.client import LangGraphClient
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import SentenceTransformerEmbeddings
from langchain_community.vectorstores.utils import DistanceStrategy
from watchfiles import awatch

# --- 로깅 설정 ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Pydantic 모델 정의 (API 입출력 형식) ---

class QueryRequest(BaseModel):
    query: str

class ColumnDescription(BaseModel):
    column_name: str
    description: str
    data_type: str
    is_primary_key: bool

class TableSearchResult(BaseModel):
    # [수정] score -> similarity_score로 이름 변경
    similarity_score: float
    table_name: str
    table_description: str
    # [추가] OpenMetadata URL 필드 추가
    openmetadata_url: str
    column_descriptions: List[ColumnDescription]

class SearchResponse(BaseModel):
    status: str
    original_query: str
    # [추가] 향후 LLM 응답을 위한 필드 추가
    llm_response: Optional[str] = None
    results: Optional[List[TableSearchResult]] = None


class ChatRequest(BaseModel):
    message: str = Field(..., description="사용자 프롬프트")
    thread_id: Optional[str] = Field(default=None, description="이어갈 LangGraph 스레드 ID")
    assistant_id: Optional[str] = Field(default=None, description="사용할 LangGraph assistant/graph ID")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="런 메타데이터")
    config: Optional[Dict[str, Any]] = Field(default=None, description="assistant 실행 설정")
    context: Optional[Dict[str, Any]] = Field(default=None, description="런타임 컨텍스트")


class ChatResponse(BaseModel):
    thread_id: str
    assistant_message: Optional[str] = None
    
class UpdateRequest(BaseModel):
    metadata_path: Optional[str] = Field(
        default="metadata/enriched_metadata_clustered.json",
        description="컨테이너 기준 메타데이터 JSON 경로",
        example="metadata/enriched_metadata_clustered.json"
    )


# --- 검색 엔진 로직 ---

def load_metadata(file_path: Path) -> List[Dict]:
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def create_and_save_faiss_index(metadata_list: List[Dict], index_path: Path, embedding_model: SentenceTransformerEmbeddings):
    """FAISS 인덱스를 생성하고 파일로 저장합니다."""
    documents, metadatas = [], []
    for table in metadata_list:
        table_name = table['name']
        column_texts = [f"- 컬럼 '{col['name']}': {col['description']}" for col in table.get('columns', [])]
        full_doc = f"테이블명: {table_name}\n테이블 설명: {table['description']}\n포함된 컬럼 정보:\n" + "\n".join(column_texts)
        documents.append(full_doc)
        metadatas.append({"type": "table", "table_name": table_name})
    
    logger.info(f"총 {len(documents)}개의 문서를 벡터로 변환합니다...")
    embeddings = embedding_model.embed_documents(documents)
    
    text_embedding_pairs = list(zip(documents, embeddings))
    
    logger.info("코사인 거리 방식으로 새로운 FAISS 인덱스를 생성합니다...")
    vector_db = FAISS.from_embeddings(
        text_embeddings=text_embedding_pairs, 
        embedding=embedding_model, 
        metadatas=metadatas, 
        distance_strategy=DistanceStrategy.COSINE
    )
    
    vector_db.save_local(str(index_path))
    logger.info(f"✅ 새로운 인덱스를 '{index_path}' 파일에 성공적으로 저장했습니다.")
    return vector_db

# [수정] OpenMetadata URL을 인자로 받아 최종 결과를 생성하도록 변경
def search_and_format_results(query: str, vector_db: FAISS, all_metadata_dict: Dict, openmetadata_base_url: str, top_k: int = 3) -> Optional[List[Dict]]:
    """벡터 검색을 수행하고 결과를 상세한 JSON 형식으로 구조화합니다."""
    similar_docs = vector_db.similarity_search_with_score(query, k=top_k)
    
    logger.info(f"🔍 벡터 DB 검색 결과 (Top {top_k}):")
    for i, (doc, score) in enumerate(similar_docs):
        log_content = doc.page_content.replace('\n', ' ')
        logger.info(f"  - [{i+1}] 유사도 점수(코사인 거리): {score:.4f}, 내용: \"{log_content[:80]}...\"")

    if not similar_docs: return None
    
    found_tables = {}
    threshold = 0.3  # 70% 이상 관련도 (1 - 0.3 = 0.7 = 70%)  
    
    # 정확한 테이블명 매칭 우선순위 처리
    query_upper = query.upper()
    exact_match_found = False
    
    # 먼저 정확한 테이블명 매칭 확인
    for doc, score in similar_docs:
        table_name = doc.metadata['table_name']
        table_name_upper = table_name.upper()
        
        # 정확한 테이블명 매칭 (대소문자 무시)
        if query_upper == table_name_upper:
            found_tables[table_name] = 0.0  # 정확한 매칭은 최고 점수
            exact_match_found = True
            logger.info(f"    -> 🎯 정확한 테이블명 매칭: '{table_name}' (점수: 0.0)")
            break
    
    # 모든 벡터 검색 결과 처리 (정확한 매칭이 있어도 나머지 유사한 결과 포함)
    for doc, score in similar_docs:
        table_name = doc.metadata['table_name']
        table_name_upper = table_name.upper()
        
        # 정확한 매칭은 이미 처리했으므로 건너뛰기
        if exact_match_found and query_upper == table_name_upper:
            continue
            
        # 임계값 통과하는 테이블들 추가
        if score < threshold:
            if table_name not in found_tables or score < found_tables[table_name]:
                found_tables[table_name] = score
                logger.info(f"    -> ✅ 임계값 통과. 테이블 '{table_name}' 추가/갱신 (점수: {score:.4f}).")

    if not found_tables and similar_docs:
        top_doc, top_score = similar_docs[0]
        table_name = top_doc.metadata['table_name']
        logger.info(f"    -> ❌ 임계값 통과 결과 없음. 가장 유사한 '{table_name}'의 점수: {top_score:.4f} (임계값: {threshold})")
        logger.info(f"    -> 관련도가 충분하지 않아 결과를 반환하지 않습니다.")
        return None  # 임계값을 넘는 결과가 없으면 빈 결과 반환

    results_list = []
    for table_name, score in sorted(found_tables.items(), key=lambda item: item[1]):
        table_data = all_metadata_dict.get(table_name)
        if table_data:
            results_list.append({
                "similarity_score": round(score, 4),
                "table_name": table_name,
                "table_description": table_data['description'],
                "openmetadata_url": f"{openmetadata_base_url}/explore/?search={table_name}&sort=_score&page=1&size=15",
                "column_descriptions": [
                    {
                        "column_name": col['name'], 
                        "description": col['description'],
                        "data_type": col.get('dataTypeDisplay', 'N/A'),
                        "is_primary_key": col.get('isPrimaryKey', False)
                    } 
                    for col in table_data.get('columns', [])
                ]
            })
    return results_list

# --- FastAPI 앱 생명주기 및 전역 변수 설정 ---
search_engine_globals = {}
_index_refresh_lock = threading.Lock()

DEFAULT_OPENMETADATA_URL = "http://localhost:8585/"
CONFIG_FILE_ENV_VAR = "OPENMETADATA_CONFIG_FILE"
METADATA_FILE_ENV_VAR = "METADATA_FILE_PATH"
FAISS_INDEX_DIR_ENV_VAR = "FAISS_INDEX_DIR"

LANGGRAPH_API_URL = "LANGGRAPH_API_URL"
LANGGRAPH_ASSISTANT_ID = "LANGGRAPH_ASSISTANT_ID"
OPENAI_API_KEY = "OPENAI_API_KEY"


async def get_langgraph_client(api_key: Optional[str] = None) -> LangGraphClient:
    """Create a LangGraph client using the provided API key (or fallback env)."""

    base_url = os.getenv(LANGGRAPH_API_URL)
    if not base_url:
        raise HTTPException(status_code=503, detail="LangGraph API URL이 설정되지 않았습니다.")

    resolved_key = api_key if api_key is not None else os.getenv(OPENAI_API_KEY)

    try:
        return get_client(url=base_url, api_key=resolved_key)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("LangGraph 클라이언트 초기화 실패: %s", exc, exc_info=True)
        raise HTTPException(status_code=503, detail="LangGraph 클라이언트를 초기화할 수 없습니다.") from exc


async def ensure_thread(client: LangGraphClient, thread_id: Optional[str]) -> str:
    """Return an existing thread id or create a fresh thread."""

    if thread_id:
        return thread_id

    thread = await client.threads.create(metadata={"source": "data-catalog-search-api"})
    return thread["thread_id"]


def extract_assistant_message(state: Dict[str, Any]) -> Optional[str]:
    """Pick the latest assistant message from the state values."""

    values = state.get("values")
    messages: Optional[List[Any]] = None

    if isinstance(values, dict):
        maybe_messages = values.get("messages")
        if isinstance(maybe_messages, list):
            messages = maybe_messages

    if not messages:
        return None

    for message in reversed(messages):
        if not isinstance(message, dict):
            continue
        role = message.get("type") or message.get("role")
        if role not in {"ai", "assistant"}:
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            segments = []
            for chunk in content:
                if isinstance(chunk, dict):
                    text = chunk.get("text")
                    if text:
                        segments.append(text)
            if segments:
                return "".join(segments)
        if isinstance(content, dict):
            text = content.get("text")
            if isinstance(text, str):
                return text

    return None


def _read_openmetadata_url_from_file(config_path: Path) -> Optional[str]:
    """Parse a simple KEY=VALUE config file and extract OPENMETADATA_BASE_URL."""
    if not config_path.exists():
        return None

    try:
        with open(config_path, "r", encoding="utf-8") as cfg:
            for raw_line in cfg:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("OPENMETADATA_BASE_URL="):
                    return line.split("=", 1)[1].strip()
                # 단일 값만 있는 경우도 허용 (예: URL만 적어둔 파일)
                if "=" not in line:
                    return line
    except Exception as exc:
        logger.warning("설정 파일 '%s'을 읽는 중 오류: %s", config_path, exc)
    return None


def load_openmetadata_base_url() -> str:
    """Resolve the current OpenMetadata base URL from environment or config file."""
    # 1) 환경 변수 우선
    env_override = os.getenv("OPENMETADATA_BASE_URL")
    if env_override:
        return env_override

    # 2) 설정 파일에서 읽기
    config_file = Path(os.getenv(CONFIG_FILE_ENV_VAR, ".env"))
    file_value = _read_openmetadata_url_from_file(config_file)
    if file_value:
        return file_value

    # 3) 기본값 반환
    return DEFAULT_OPENMETADATA_URL


def derive_faiss_index_path(metadata_path: Path) -> Path:
    base_dir = Path(os.getenv(FAISS_INDEX_DIR_ENV_VAR, "faiss_indices"))
    safe_stem = metadata_path.stem.replace(" ", "_").replace(".", "_")
    return base_dir / safe_stem


def refresh_faiss_index_if_needed(metadata_path: Optional[Path] = None) -> Dict[str, str]:
    """Rebuild the FAISS index if the metadata JSON changed.

    Returns a dict with keys:
        status: "updated" or "skipped"
        detail: human-readable explanation
    Raises HTTPException on hard failures (missing config, JSON error, etc.).
    """
    metadata_path = Path(metadata_path) if metadata_path else search_engine_globals.get('metadata_path')
    embedding_model: Optional[SentenceTransformerEmbeddings] = search_engine_globals.get('embedding_model')

    if metadata_path is None or embedding_model is None:
        logger.error("메타데이터 경로 또는 인덱스 설정이 초기화되지 않았습니다.")
        raise HTTPException(status_code=503, detail="Metadata or index configuration is missing.")

    metadata_path = metadata_path if isinstance(metadata_path, Path) else Path(metadata_path)
    metadata_mtime_map: Dict[str, float] = search_engine_globals.setdefault('metadata_mtime_map', {})
    metadata_key = str(metadata_path.resolve())

    path_changed = search_engine_globals.get('metadata_path') != metadata_path
    if path_changed:
        search_engine_globals['metadata_path'] = metadata_path
        search_engine_globals['faiss_index_path'] = derive_faiss_index_path(metadata_path)
        search_engine_globals['metadata_mtime'] = metadata_mtime_map.get(metadata_key)
        search_engine_globals.pop('vector_db', None)

    faiss_index_path: Optional[Path] = search_engine_globals.get('faiss_index_path')
    if faiss_index_path is None:
        faiss_index_path = derive_faiss_index_path(metadata_path)
        search_engine_globals['faiss_index_path'] = faiss_index_path

    try:
        current_mtime = metadata_path.stat().st_mtime
    except FileNotFoundError:
        msg = f"메타데이터 파일 '{metadata_path}'을 찾을 수 없습니다."
        logger.error(msg)
        raise HTTPException(status_code=404, detail=msg)

    last_mtime = search_engine_globals.get('metadata_mtime')
    index_exists = faiss_index_path.exists()
    if not path_changed and index_exists and last_mtime and current_mtime <= last_mtime:
        return {"status": "skipped", "detail": "Metadata unchanged."}

    with _index_refresh_lock:
        last_mtime = search_engine_globals.get('metadata_mtime')
        index_exists = faiss_index_path.exists()
        if path_changed and index_exists:
            cached_mtime = metadata_mtime_map.get(metadata_key)
            if cached_mtime and current_mtime <= cached_mtime:
                logger.info("📂 기존 FAISS 인덱스를 로드합니다: %s", faiss_index_path)
                metadata = load_metadata(metadata_path)
                search_engine_globals['metadata_dict'] = {table['name']: table for table in metadata}

                search_engine_globals['vector_db'] = FAISS.load_local(
                    str(faiss_index_path),
                    embedding_model,
                    allow_dangerous_deserialization=True,
                    distance_strategy=DistanceStrategy.COSINE
                )
                search_engine_globals['metadata_mtime'] = cached_mtime
                return {"status": "loaded", "detail": "Existing FAISS index loaded for metadata path."}

        if not path_changed and index_exists and last_mtime and current_mtime <= last_mtime:
            return {"status": "skipped", "detail": "Metadata unchanged."}

        logger.info("📁 메타데이터 파일 변경 감지. FAISS 인덱스를 재생성합니다...")
        try:
            metadata = load_metadata(metadata_path)
        except json.JSONDecodeError as exc:
            msg = f"메타데이터 JSON 파싱 실패: {exc}"
            logger.error(msg)
            raise HTTPException(status_code=400, detail=msg)

        search_engine_globals['metadata_dict'] = {table['name']: table for table in metadata}

        faiss_index_path.parent.mkdir(parents=True, exist_ok=True)
        search_engine_globals['vector_db'] = create_and_save_faiss_index(metadata, faiss_index_path, embedding_model)
        search_engine_globals['metadata_mtime'] = current_mtime
        metadata_mtime_map[metadata_key] = current_mtime
        logger.info("✅ 메타데이터 및 인덱스가 최신 상태로 갱신되었습니다.")
        return {"status": "updated", "detail": "Metadata and FAISS index refreshed."}


async def monitor_openmetadata_base_url():
    """Watch the config file for changes and refresh the OpenMetadata URL in realtime."""
    config_file = Path(os.getenv(CONFIG_FILE_ENV_VAR, ".env")).resolve()
    config_file.parent.mkdir(parents=True, exist_ok=True)

    watch_target = config_file if config_file.exists() else config_file.parent
    last_value = search_engine_globals.get("openmetadata_base_url")

    logger.info("🔍 '%s' 감시를 시작합니다.", watch_target)

    async for changes in awatch(watch_target):
        relevant_change = False
        config_path_resolved = config_file.resolve()
        for _change, changed_path in changes:
            if Path(changed_path).resolve() == config_path_resolved:
                relevant_change = True
                break

        if not relevant_change and watch_target == config_file:
            # watch_target이 파일인데 다른 변경이면 무시
            continue

        current_value = _read_openmetadata_url_from_file(config_file) or DEFAULT_OPENMETADATA_URL
        if current_value != last_value:
            search_engine_globals["openmetadata_base_url"] = current_value
            logger.info("🔁 OpenMetadata URL 업데이트: %s", current_value)
            last_value = current_value
        else:
            logger.info("🔁 OpenMetadata 설정 파일이 갱신되었지만 URL은 변경되지 않았습니다.")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 서버 시작: 검색 엔진을 설정합니다...")
    
    # OpenMetadata URL 초기화 및 동적 갱신 태스크 시작
    initial_url = load_openmetadata_base_url()
    search_engine_globals['openmetadata_base_url'] = initial_url
    logger.info(f"OpenMetadata 기본 URL: {initial_url}")

    METADATA_FILE_PATH = Path(os.getenv(METADATA_FILE_ENV_VAR, 'metadata/enriched_metadata_clustered.json'))
    FAISS_INDEX_PATH = derive_faiss_index_path(METADATA_FILE_PATH)

    search_engine_globals['metadata_path'] = METADATA_FILE_PATH
    search_engine_globals['faiss_index_path'] = FAISS_INDEX_PATH

    all_metadata = load_metadata(METADATA_FILE_PATH)
    search_engine_globals['metadata_dict'] = {table['name']: table for table in all_metadata}
    
    logger.info("E5-Small 임베딩 모델을 로드합니다...")
    embedding_model = SentenceTransformerEmbeddings(
        model_name="intfloat/multilingual-e5-small",
        model_kwargs={"device": "cpu"}
    )
    search_engine_globals['embedding_model'] = embedding_model

    vector_db = None
    if not FAISS_INDEX_PATH.exists():
        FAISS_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
        logger.warning(f"인덱스 파일 '{FAISS_INDEX_PATH}'를 찾을 수 없습니다. 새로 생성합니다.")
        vector_db = create_and_save_faiss_index(all_metadata, FAISS_INDEX_PATH, embedding_model)
    
    if vector_db is None:
        logger.info(f"'{FAISS_INDEX_PATH}'에서 인덱스를 로드합니다...")
        vector_db = FAISS.load_local(
            str(FAISS_INDEX_PATH), 
            embedding_model, 
            allow_dangerous_deserialization=True,
            distance_strategy=DistanceStrategy.COSINE 
        )

    search_engine_globals['vector_db'] = vector_db

    try:
        search_engine_globals['metadata_mtime'] = METADATA_FILE_PATH.stat().st_mtime
    except FileNotFoundError:
        search_engine_globals['metadata_mtime'] = None
    
    if search_engine_globals.get('metadata_mtime') is not None:
        metadata_mtime_map = search_engine_globals.setdefault('metadata_mtime_map', {})
        metadata_mtime_map[str(METADATA_FILE_PATH.resolve())] = search_engine_globals['metadata_mtime']

    logger.info("✅ 검색 엔진 준비 완료.")

    config_task = None
    if os.getenv("OPENMETADATA_BASE_URL"):
        logger.info("환경 변수 OPENMETADATA_BASE_URL이 설정되어 있어 파일 변경 감시를 비활성화합니다.")
    else:
        config_task = asyncio.create_task(monitor_openmetadata_base_url())
    try:
        yield
    finally:
        if config_task:
            config_task.cancel()
            with suppress(asyncio.CancelledError):
                await config_task
        search_engine_globals.clear()
        logger.info("👋 서버 종료.")

# --- FastAPI 앱 인스턴스 생성 ---
app = FastAPI(
    title="메타데이터 검색 API (E5-small)",
    description="자연어 쿼리를 사용하여 테이블 및 컬럼 정보를 검색합니다.",
    version="2.8", # 버전 업데이트
    lifespan=lifespan
)

# --- CORS 설정 추가 ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 모든 도메인에서 접근 허용
    allow_credentials=True,
    allow_methods=["*"],  # 모든 HTTP 메서드 허용
    allow_headers=["*"],  # 모든 헤더 허용
)

# --- API 엔드포인트 ---
@app.post("/search", response_model=SearchResponse)
async def search_metadata(request: QueryRequest):
    query = request.query
    logger.info(f"📬 수신된 쿼리: {query}")
    vector_db = search_engine_globals.get('vector_db')
    metadata_dict = search_engine_globals.get('metadata_dict')
    openmetadata_base_url = search_engine_globals.get('openmetadata_base_url')

    if not all([vector_db, metadata_dict, openmetadata_base_url]):
        raise HTTPException(status_code=503, detail="검색 엔진이 아직 준비되지 않았습니다.")
        
    try:
        search_results = search_and_format_results(query, vector_db, metadata_dict, openmetadata_base_url)
        return SearchResponse(
            status="success", 
            original_query=query, 
            # [추가] llm_response 필드에 기본값 추가
            llm_response="LLM 응답은 향후 추가될 예정입니다.",
            results=search_results
        )
    except Exception as e:
        logger.error(f"검색 중 오류 발생: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="검색 처리 중 내부 오류가 발생했습니다.")


@app.post("/chat", response_model=ChatResponse)
async def chat_with_langgraph(payload: ChatRequest, request: Request) -> ChatResponse:
    """Proxy chat requests to a LangGraph assistant."""
    
    assistant_id = payload.assistant_id or os.getenv(LANGGRAPH_ASSISTANT_ID)
    if not assistant_id:
        raise HTTPException(status_code=500, detail="LangGraph assistant ID가 설정되지 않았습니다.")

    api_key = request.headers.get("x-api-key")
    logger.info(
        "💬 /chat 시작: assistant_id=%s, thread=%s, has_api_key=%s",
        assistant_id,
        payload.thread_id,
        bool(api_key),
    )
    client = await get_langgraph_client(api_key=api_key)

    try:
        thread_id = await ensure_thread(client, payload.thread_id)
        logger.info("🧵 thread 준비 완료: %s", thread_id)

        config_payload: Optional[Dict[str, Any]] = payload.config.copy() if payload.config else {}
        if config_payload is not None:
            configurable = dict(config_payload.get("configurable", {}))
        else:
            configurable = {}
        if api_key:
            configurable.setdefault("openai_api_key", api_key)
        if assistant_id:
            configurable.setdefault("assistant_id", assistant_id)
        if configurable:
            if config_payload is None:
                config_payload = {}
            config_payload["configurable"] = configurable
        elif config_payload is not None and "configurable" in config_payload:
            config_payload.pop("configurable")

        if config_payload == {}:
            config_payload = None

        logger.info(
            "🚀 runs.wait 호출: thread=%s, assistant=%s, metadata=%s, config=%s",
            thread_id,
            assistant_id,
            payload.metadata,
            config_payload,
        )
        await client.runs.wait(
            thread_id=thread_id,
            assistant_id=assistant_id,
            input={"messages": [{"role": "user", "content": payload.message}]},
            metadata=payload.metadata,
            config=config_payload,
            context=payload.context,
        )

        state = await client.threads.get_state(thread_id=thread_id)
        logger.debug("📥 threads.get_state 완료: %s", state)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("LangGraph 챗 실행 중 오류: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="LangGraph 실행 중 오류가 발생했습니다.") from exc
    finally:
        with suppress(Exception):
            await client.aclose()
        logger.debug("🔚 LangGraph 클라이언트 종료")

    raw_metadata = state.get("metadata")
    metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
    assistant_message = extract_assistant_message(state)
    logger.debug("💡 assistant_message=%s", assistant_message)

    return ChatResponse(
        thread_id=thread_id,
        assistant_message=assistant_message,
    )


@app.post("/update")
async def trigger_metadata_refresh(body: UpdateRequest = UpdateRequest()):
    logger.info("📦 /update 요청 수신: 메타데이터 및 인덱스를 갱신합니다.")

    metadata_path = Path(body.metadata_path) if body.metadata_path else None
    result = refresh_faiss_index_if_needed(metadata_path)

    if 'vector_db' not in search_engine_globals:
        logger.error("FAISS 인덱스가 초기화되지 않았습니다.")
        raise HTTPException(status_code=503, detail="검색 엔진이 아직 준비되지 않았습니다.")

    return result
