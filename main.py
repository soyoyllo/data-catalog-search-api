import json
import logging
import os
from contextlib import asynccontextmanager
from typing import List, Dict, Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import SentenceTransformerEmbeddings
from langchain_community.vectorstores.utils import DistanceStrategy

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
    threshold = 0.5
    for doc, score in similar_docs:
        table_name = doc.metadata['table_name']
        if score < threshold:
            if table_name not in found_tables or score < found_tables[table_name]:
                found_tables[table_name] = score
                logger.info(f"    -> ✅ 임계값 통과. 테이블 '{table_name}' 추가/갱신 (점수: {score:.4f}).")

    if not found_tables and similar_docs:
        top_doc, top_score = similar_docs[0]
        table_name = top_doc.metadata['table_name']
        found_tables[table_name] = top_score
        logger.info(f"    -> ⚠️ 임계값 통과 결과 없음. 가장 유사한 '{table_name}'을(를) 대신 반환합니다.")

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

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 서버 시작: 검색 엔진을 설정합니다...")
    
    # [추가] 환경 변수에서 OpenMetadata URL을 읽어옵니다.
    OPENMETADATA_BASE_URL = os.getenv("OPENMETADATA_BASE_URL", "https://de4f5334deb3.ngrok-free.app/my-data")
    search_engine_globals['openmetadata_base_url'] = OPENMETADATA_BASE_URL
    logger.info(f"OpenMetadata 기본 URL: {OPENMETADATA_BASE_URL}")

    METADATA_FILE_PATH = Path('metadata/enriched_metadata_clustered.json')
    FAISS_INDEX_PATH = Path("faiss_indices/faiss_index_e5_small") 

    all_metadata = load_metadata(METADATA_FILE_PATH)
    search_engine_globals['metadata_dict'] = {table['name']: table for table in all_metadata}
    
    logger.info("E5-Small 임베딩 모델을 로드합니다...")
    embedding_model = SentenceTransformerEmbeddings(
        model_name="intfloat/multilingual-e5-small"
    )
    
    if not FAISS_INDEX_PATH.exists():
        FAISS_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
        logger.warning(f"인덱스 파일 '{FAISS_INDEX_PATH}'를 찾을 수 없습니다. 새로 생성합니다.")
        create_and_save_faiss_index(all_metadata, FAISS_INDEX_PATH, embedding_model)
    
    logger.info(f"'{FAISS_INDEX_PATH}'에서 인덱스를 로드합니다...")
    search_engine_globals['vector_db'] = FAISS.load_local(
        str(FAISS_INDEX_PATH), 
        embedding_model, 
        allow_dangerous_deserialization=True,
        distance_strategy=DistanceStrategy.COSINE 
    )
    
    logger.info("✅ 검색 엔진 준비 완료.")
    yield
    search_engine_globals.clear()
    logger.info("👋 서버 종료.")

# --- FastAPI 앱 인스턴스 생성 ---
app = FastAPI(
    title="메타데이터 검색 API (E5-small)",
    description="자연어 쿼리를 사용하여 테이블 및 컬럼 정보를 검색합니다.",
    version="2.8", # 버전 업데이트
    lifespan=lifespan
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

