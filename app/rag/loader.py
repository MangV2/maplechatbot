"""MapleRAG 싱글톤 인스턴스 관리."""
import logging

from app.config import settings
from app.rag.maple_rag import MapleRAG
from app.rag.openai_client import OpenAIClient
from app.rag.qdrant_store import QdrantStore

logger = logging.getLogger(__name__)

_rag_instance: MapleRAG | None = None


def _load_rag() -> MapleRAG:
    """Qdrant + OpenAI 기반 MapleRAG 인스턴스 생성."""
    store = QdrantStore()
    ai = OpenAIClient()

    # Qdrant에서 직업 목록 가져오기
    try:
        job_list = store.get_unique_jobs()
        logger.info("직업 목록 로드 완료: %d개", len(job_list))
    except Exception as e:
        logger.warning("직업 목록 로드 실패 (빈 목록 사용): %s", e)
        job_list = []

    doc_count = store.count()
    logger.info("MapleRAG 초기화 완료 (Qdrant 문서 수: %d)", doc_count)

    return MapleRAG(qdrant_store=store, openai_client=ai, job_list=job_list)


def get_rag() -> MapleRAG:
    """MapleRAG 싱글톤 (첫 호출 시 로드)."""
    global _rag_instance
    if _rag_instance is None:
        _rag_instance = _load_rag()
    return _rag_instance


def reset_rag():
    """싱글톤 초기화 (테스트용 또는 데이터 갱신 후 리로드)."""
    global _rag_instance
    _rag_instance = None
    logger.info("MapleRAG 싱글톤 초기화됨")
